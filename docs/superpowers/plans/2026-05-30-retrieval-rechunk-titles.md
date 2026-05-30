# Retrieval Step 1+2: Token-Chunking + Title Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lift retrieval recall (baseline hit@5 0.25) by re-chunking the EN corpus at the embedder's real token budget instead of 512 *characters*, and re-ingest the gte index carrying `document_title`/`section_heading` metadata so the citation guard can validate real titles.

**Architecture:** The shared chunker (`ingestion/chunker.py`) currently sizes chunks with `length_function=len` — characters, ~100 tokens, ¼ of `gte-base`'s 512-token budget. Switch it to count tokens with the gte tokenizer (~480 tokens/chunk). Rebuild the gte index **into a new index** `agroar-prod-gte-v2` from the raw PDFs (single source of truth) carrying full metadata — never clobber the live `agroar-prod-gte`. Because new chunk boundaries produce new `chunk_id`s, a deterministic remap regenerates the eval gold (old gold `chunk_text` → new containing chunk) so the retrieval delta is measured on the **same 200 queries** without any LLM/Groq calls. Cutover to prod is a gated env-var flip after a positive eval delta.

**Tech Stack:** Python, `langchain-text-splitters` (`RecursiveCharacterTextSplitter.from_huggingface_tokenizer`), `transformers` (gte tokenizer), `sentence-transformers` (gte-base embedder), Pinecone, pytest.

---

## Why a new index, not in-place

`agroar-prod-gte` serves live prod traffic. Rebuilding in place = downtime + no rollback. Build `agroar-prod-gte-v2`, eval it, then cut over via `PINECONE_INDEX_NAME` env (instant rollback). Mirrors the original MiniLM→gte cutover.

## Constraint: Groq TPD exhausted today

`answer_eval.py` (full RAG + judge) needs Groq generation — daily free cap is spent (`Limit 100000, Used 99499`). So **today** we measure the **retrieval** delta only (embed + Pinecone, no LLM), via the remapped eval set. The answer-correctness delta runs when the TPD resets (or on a paid Dev tier).

## File Structure

- `ingestion/chunker.py` — MODIFY: token-based splitter (lazy gte tokenizer).
- `ingestion/ingest_en_gte.py` — MODIFY: build chunks from `raw_pdfs/` via `chunk_document`; upsert `document_title`+`section_heading`; index name from env (default `agroar-prod-gte-v2`).
- `evals/remap_eval_set.py` — CREATE: deterministic old-gold→new-chunk remap, no LLM.
- `backend/tests/test_chunker_tokenization.py` — CREATE: token-size contract.
- `ingestion/tests/test_ingest_gte_metadata.py` — CREATE: metadata-builder unit test.
- `evals/tests/test_remap_eval_set.py` — CREATE: remap containment unit test.

---

## Task 1: Token-based chunker

**Files:**
- Modify: `ingestion/chunker.py`
- Test: `backend/tests/test_chunker_tokenization.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_chunker_tokenization.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ingestion"))

from transformers import AutoTokenizer
from chunker import chunk_document

_TOK = AutoTokenizer.from_pretrained("thenlper/gte-base")


def _long_text():
    # ~6000 tokens of varied agronomic prose so the splitter must produce many chunks.
    para = (
        "Sprayer calibration is essential for accurate herbicide application. "
        "Determine gallons per acre using the ounce method before mixing the tank. "
        "Nitrogen deficiency in rice shows as yellowing of the lower leaves. "
    )
    return (para * 200)


def test_chunks_sized_near_gte_token_budget():
    docs = chunk_document(
        _long_text(),
        document_title="test doc",
        source_url="file://x",
        crop_type="rice",
    )
    assert len(docs) > 1
    token_lens = [len(_TOK.encode(d.page_content, add_special_tokens=False)) for d in docs]
    # No chunk exceeds the gte-base 512-token input budget.
    assert max(token_lens) <= 512
    # Chunks are substantial — mean well above the old ~100-token (512-char) regime.
    assert sum(token_lens) / len(token_lens) > 300
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_chunker_tokenization.py -q`
Expected: FAIL — current char-based splitter yields mean chunk length ~100 tokens, so `mean > 300` assertion fails.

- [ ] **Step 3: Write minimal implementation**

Replace the splitter in `ingestion/chunker.py`. Old:

```python
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=["\n\n", "\n", ". ", " ", ""],
)
```

New (lazy gte-tokenizer splitter — counts tokens, matching the embedder's real budget):

```python
# Size chunks by the gte-base tokenizer (the embedder), not characters. gte-base
# truncates input at 512 tokens; the old 512-CHAR splitter produced ~100-token
# chunks (¼ the budget), fragmenting answers across near-duplicate vectors and
# starving retrieval recall. 480 tokens leaves headroom for special tokens.
CHUNK_TOKENS = 480
CHUNK_OVERLAP_TOKENS = 64
_EMBED_TOKENIZER = "thenlper/gte-base"

_splitter = None


def _get_splitter():
    global _splitter
    if _splitter is None:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(_EMBED_TOKENIZER)
        _splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            tok,
            chunk_size=CHUNK_TOKENS,
            chunk_overlap=CHUNK_OVERLAP_TOKENS,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
    return _splitter
```

And in `chunk_document`, change the split call from `_splitter.split_text(text)` to `_get_splitter().split_text(text)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_chunker_tokenization.py -q`
Expected: PASS (loads cached gte tokenizer; first run may download ~1s).

- [ ] **Step 5: Commit**

```bash
git add ingestion/chunker.py backend/tests/test_chunker_tokenization.py
git commit -m "feat(ingest): size chunks by gte token budget, not characters"
```

---

## Task 2: gte ingest from raw PDFs with title metadata

**Files:**
- Modify: `ingestion/ingest_en_gte.py`
- Test: `ingestion/tests/test_ingest_gte_metadata.py`

- [ ] **Step 1: Write the failing test**

```python
# ingestion/tests/test_ingest_gte_metadata.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.documents import Document
from ingest_en_gte import build_vector


def test_build_vector_carries_title_and_section():
    doc = Document(
        page_content="Calibrate the sprayer before applying herbicide.",
        metadata={
            "chunk_id": "abc123",
            "document_title": "soybeans recommended chemicals 2024",
            "section_heading": "Sprayer Calibration",
            "crop_type": "soybeans",
        },
    )
    vec = build_vector(doc, embedding=[0.1, 0.2, 0.3])
    assert vec["id"] == "abc123"
    assert vec["values"] == [0.1, 0.2, 0.3]
    assert vec["metadata"]["text"] == "Calibrate the sprayer before applying herbicide."
    assert vec["metadata"]["namespace"] == "soybeans"
    assert vec["metadata"]["document_title"] == "soybeans recommended chemicals 2024"
    assert vec["metadata"]["section_heading"] == "Sprayer Calibration"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ingestion && python -m pytest tests/test_ingest_gte_metadata.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_vector'`.

- [ ] **Step 3: Write minimal implementation**

Rewrite `ingestion/ingest_en_gte.py` to build from raw PDFs (single source of truth) carrying full metadata. Replace the whole file body below the docstring:

```python
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer
from langchain_core.documents import Document

from extractor import extract_text, extract_tables_as_text
from chunker import chunk_document

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
# Build into a NEW index by default — never clobber the live agroar-prod-gte.
INDEX_NAME = os.environ.get("EN_GTE_INDEX_NAME", "agroar-prod-gte-v2")
MODEL_NAME = os.environ.get("EN_GTE_MODEL", "thenlper/gte-base")
RAW_PDFS_DIR = Path(__file__).parent / "raw_pdfs"
BATCH_SIZE = 64
DIMENSION = 768

CROP_PREFIXES = {"rice", "soybeans", "poultry", "general"}


def _infer_crop_type(filename: str) -> str:
    name = filename.lower()
    for crop in CROP_PREFIXES:
        if name.startswith(crop + "_") or name.startswith(crop + "-"):
            return crop
    return "general"


def build_vector(doc: Document, embedding: list) -> dict:
    """Pinecone vector dict for one chunk, carrying title/section metadata so the
    citation guard can validate real document titles."""
    ns = doc.metadata["crop_type"]
    return {
        "id": doc.metadata["chunk_id"],
        "values": embedding,
        "metadata": {
            "text": doc.page_content,
            "namespace": ns,
            "document_title": doc.metadata.get("document_title", ""),
            "section_heading": doc.metadata.get("section_heading", ""),
        },
    }


def _chunk_all_pdfs() -> list:
    docs = []
    for pdf_path in sorted(RAW_PDFS_DIR.glob("*.pdf")):
        crop = _infer_crop_type(pdf_path.name)
        text = extract_text(str(pdf_path))
        tables = extract_tables_as_text(str(pdf_path))
        if tables:
            text += "\n\n" + "\n\n".join(tables)
        title = pdf_path.stem.replace("_", " ").replace("-", " ")
        docs.extend(chunk_document(
            text, document_title=title,
            source_url=f"file://{pdf_path.resolve()}", crop_type=crop,
        ))
    return docs


def _get_or_create_index(pc: Pinecone):
    if INDEX_NAME not in [i.name for i in pc.list_indexes()]:
        print(f"Creating index '{INDEX_NAME}' ({DIMENSION}-dim, cosine)...")
        pc.create_index(
            name=INDEX_NAME, dimension=DIMENSION, metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(INDEX_NAME).status["ready"]:
            time.sleep(1)
    return pc.Index(INDEX_NAME)


def main() -> int:
    docs = _chunk_all_pdfs()
    if not docs:
        print(f"No chunks built from {RAW_PDFS_DIR}.")
        return 0
    print(f"Built {len(docs)} chunks from raw PDFs. Loading {MODEL_NAME}...")
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(MODEL_NAME, device=device)
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = _get_or_create_index(pc)

    total = 0
    for i in range(0, len(docs), BATCH_SIZE):
        batch = docs[i:i + BATCH_SIZE]
        embs = model.encode(
            [d.page_content for d in batch],
            normalize_embeddings=True, batch_size=BATCH_SIZE,
        ).tolist()
        by_ns: dict[str, list] = {}
        for d, emb in zip(batch, embs):
            v = build_vector(d, emb)
            by_ns.setdefault(v["metadata"]["namespace"], []).append(v)
        for ns, vecs in by_ns.items():
            index.upsert(vectors=vecs, namespace=ns)
            total += len(vecs)
        print(f"  {min(i + BATCH_SIZE, len(docs))}/{len(docs)} upserted")

    print(f"\nTotal upserted: {total} vectors to '{INDEX_NAME}'")
    return total


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ingestion && python -m pytest tests/test_ingest_gte_metadata.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ingestion/ingest_en_gte.py ingestion/tests/test_ingest_gte_metadata.py
git commit -m "feat(ingest): rebuild gte from raw PDFs with title/section metadata"
```

---

## Task 3: Deterministic eval-set remap (no LLM)

**Files:**
- Create: `evals/remap_eval_set.py`
- Test: `evals/tests/test_remap_eval_set.py`

Maps each eval item's old gold `chunk_text` to the new chunk that best contains it (token-overlap, same namespace), so retrieval eval runs on the **same queries** against the new index.

- [ ] **Step 1: Write the failing test**

```python
# evals/tests/test_remap_eval_set.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from remap_eval_set import best_new_chunk_id


class _Doc:
    def __init__(self, cid, ns, text):
        self.metadata = {"chunk_id": cid, "crop_type": ns}
        self.page_content = text


def test_picks_chunk_containing_the_gold_span():
    new = [
        _Doc("n1", "rice", "Totally unrelated poultry ventilation content here."),
        _Doc("n2", "rice", "Before mixing, calibrate the sprayer accurately. "
                            "Determine gallons per acre using the ounce method."),
    ]
    gold = "calibrate the sprayer accurately"
    assert best_new_chunk_id(gold, "rice", new) == "n2"


def test_respects_namespace():
    new = [
        _Doc("p1", "poultry", "calibrate the sprayer accurately ounce method"),
        _Doc("r1", "rice", "calibrate the sprayer accurately ounce method"),
    ]
    assert best_new_chunk_id("calibrate the sprayer", "rice", new) == "r1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd evals && python -m pytest tests/test_remap_eval_set.py -q`
Expected: FAIL — `ImportError: cannot import name 'best_new_chunk_id'`.

- [ ] **Step 3: Write minimal implementation**

```python
# evals/remap_eval_set.py
"""Remap eval_set_v2 gold chunk_ids onto a re-chunked corpus WITHOUT an LLM.

After token re-chunking, the old 512-char gold chunk_ids no longer exist. Each
eval item still carries the gold `chunk_text`; this finds the new chunk (same
namespace) with the highest token overlap with that gold span and rewrites the
item's chunk_id. Lets retrieval eval run on the identical 200 queries against
the new index for a true apples-to-apples delta.

Run: python evals/remap_eval_set.py --out evals/eval_set_v2_remap.jsonl
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "ingestion"))

from extractor import extract_text, extract_tables_as_text  # noqa: E402
from chunker import chunk_document  # noqa: E402

RAW_PDFS_DIR = Path(__file__).parent.parent / "ingestion" / "raw_pdfs"
DEFAULT_EVAL = Path(__file__).parent / "eval_set_v2.jsonl"
CROP_PREFIXES = {"rice", "soybeans", "poultry", "general"}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _toks(text: str) -> set:
    return set(_TOKEN_RE.findall(text.lower()))


def _infer_crop_type(filename: str) -> str:
    name = filename.lower()
    for crop in CROP_PREFIXES:
        if name.startswith(crop + "_") or name.startswith(crop + "-"):
            return crop
    return "general"


def best_new_chunk_id(gold_text: str, namespace: str, new_docs: list) -> str | None:
    """chunk_id of the same-namespace new chunk with max token overlap vs gold."""
    gold = _toks(gold_text)
    if not gold:
        return None
    best_id, best_score = None, 0.0
    for d in new_docs:
        if d.metadata.get("crop_type") != namespace:
            continue
        overlap = len(gold & _toks(d.page_content)) / len(gold)
        if overlap > best_score:
            best_id, best_score = d.metadata["chunk_id"], overlap
    return best_id


def _chunk_all_pdfs() -> list:
    docs = []
    for pdf_path in sorted(RAW_PDFS_DIR.glob("*.pdf")):
        crop = _infer_crop_type(pdf_path.name)
        text = extract_text(str(pdf_path))
        tables = extract_tables_as_text(str(pdf_path))
        if tables:
            text += "\n\n" + "\n\n".join(tables)
        title = pdf_path.stem.replace("_", " ").replace("-", " ")
        docs.extend(chunk_document(
            text, document_title=title,
            source_url=f"file://{pdf_path.resolve()}", crop_type=crop,
        ))
    return docs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "eval_set_v2_remap.jsonl")
    args = ap.parse_args()

    items = [json.loads(l) for l in open(args.eval_set, encoding="utf-8")]
    new_docs = _chunk_all_pdfs()
    print(f"Re-chunked {len(new_docs)} new chunks; remapping {len(items)} eval items...")

    out, dropped = [], 0
    for it in items:
        nid = best_new_chunk_id(it["chunk_text"], it["namespace"], new_docs)
        if nid is None:
            dropped += 1
            continue
        out.append({**it, "chunk_id": nid})

    with open(args.out, "w", encoding="utf-8") as f:
        for it in out:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"Wrote {len(out)} remapped items ({dropped} dropped) -> {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd evals && python -m pytest tests/test_remap_eval_set.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add evals/remap_eval_set.py evals/tests/test_remap_eval_set.py
git commit -m "feat(evals): deterministic eval-set remap for re-chunked corpus"
```

---

## Task 4: Build the v2 index + measure the retrieval delta

No code — execution + measurement. (Runs the real ingest + eval; Pinecone resource, reversible.)

- [ ] **Step 1: Build the v2 index from raw PDFs**

Run: `cd ingestion && python ingest_en_gte.py`
Expected: `Total upserted: <N> vectors to 'agroar-prod-gte-v2'`, where **N is far below 20,546** (token chunks are ~4× larger → ~5,000–8,000 chunks). This drop is the sanity signal that token-chunking worked.

- [ ] **Step 2: Sanity-check title metadata landed**

```bash
cd ingestion && python -c "import os; from pinecone import Pinecone; from dotenv import load_dotenv; load_dotenv('../.env'); idx=Pinecone(api_key=os.environ['PINECONE_API_KEY']).Index('agroar-prod-gte-v2'); r=idx.query(vector=[0.0]*768, top_k=1, namespace='rice', include_metadata=True); print(r['matches'][0]['metadata'].keys() if r['matches'] else 'EMPTY')"
```
Expected: keys include `document_title` and `section_heading`.

- [ ] **Step 3: Remap the eval set onto the new chunks**

Run: `cd evals && python remap_eval_set.py --out eval_set_v2_remap.jsonl`
Expected: `Wrote ~200 remapped items` (a handful may drop).

- [ ] **Step 4: Run retrieval eval on the v2 index (same 200 queries)**

Run:
```bash
cd "<repo root>" && EMBEDDING_MODEL_PATH=thenlper/gte-base PINECONE_INDEX_NAME=agroar-prod-gte-v2 \
  python evals/eval_runner.py --eval-set evals/eval_set_v2_remap.jsonl
```
Expected: results saved to `evals/results/`. **GATE: hit@5 must beat the 0.25 baseline** (target ≥0.45). Record MRR@5 / hit@1 / hit@5.

- [ ] **Step 5: Record the delta**

Append the before/after row (baseline 0.25 → new) to `[[project-answer-quality]]` memory and `docs/status-bar.md`. If hit@5 regressed, STOP — do not cut over; investigate (likely chunk too large diluting the embedding, or remap mismatch).

---

## Task 5: Gated prod cutover (deferred)

Only after Task 4 shows a positive retrieval delta AND (when Groq TPD resets) `answer_eval.py --sample 20` on the v2 index beats ~27%.

- [ ] **Step 1:** Set HF Space env `PINECONE_INDEX_NAME=agroar-prod-gte-v2` (keep `EMBEDDING_MODEL_PATH=thenlper/gte-base`).
- [ ] **Step 2:** Browser smoke test EN + ES (one grounded query each; confirm a real citation renders, confidence not floored).
- [ ] **Step 3:** Rollback path documented: revert env to `agroar-prod-gte`. Leave the old index in place until v2 is proven in prod.

---

## Self-Review

**Spec coverage:**
- Step 1 (token chunking) → Task 1. ✓
- Step 2 (title/section metadata in gte) → Task 2. ✓
- Measurement on same queries despite id change → Task 3 (remap) + Task 4. ✓
- Don't clobber prod → new index `agroar-prod-gte-v2`, gated cutover Task 5. ✓
- Groq-exhausted constraint → retrieval-only delta today; answer-eval deferred to Task 5. ✓

**Type/name consistency:** `build_vector(doc, embedding)` defined in Task 2, used in Task 2 main. `best_new_chunk_id(gold_text, namespace, new_docs)` defined + used in Task 3. `chunk_document(text, document_title=, source_url=, crop_type=)` signature matches `ingestion/chunker.py`. Index name `agroar-prod-gte-v2` consistent across Tasks 2/4/5. `_chunk_all_pdfs` duplicated in ingest + remap by design (different packages, no shared import path) — acceptable, documented.

**Placeholders:** none — all steps carry real code/commands.

**Known limitation (documented, not a gap):** `section_heading` stays `""` (the chunker/pipeline never extracts real headings). Step 2 delivers `document_title` (what the guard checks); real section extraction is a separate future task, intentionally out of scope.
