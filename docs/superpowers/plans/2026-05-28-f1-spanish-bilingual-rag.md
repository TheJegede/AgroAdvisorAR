# F1 Spanish Bilingual RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Spanish-language RAG support — BGE-M3 multilingual embeddings routed to a separate Pinecone index, `langdetect`-based query routing, Layer A MT-translated corpus, and an AR-AgQA-ES eval benchmark.

**Architecture:** `langdetect.detect()` classifies each query as 'es' or 'en' after sanitization. Spanish queries use `BGEEmbeddings` (1024-dim BAAI/bge-m3) against a new `agroar-prod-multilingual` Pinecone index; English queries continue using the fine-tuned MiniLM v2 against `agroar-prod`. The ingestion pipeline gets `--lang`/`--index` CLI flags for native Spanish PDFs (Layers B/C). A separate MT script generates Layer A Spanish chunks from the existing EN corpus.

**Tech Stack:** `BAAI/bge-m3` (sentence-transformers), `langdetect==1.0.9`, `Helsinki-NLP/opus-mt-en-es` (HuggingFace transformers), Pinecone Serverless (1024-dim), FastAPI, pytest

---

## File Map

| File | Change |
|---|---|
| `backend/config.py` | Add `PINECONE_MULTILINGUAL_INDEX_NAME`, `MULTILINGUAL_EMBEDDING_MODEL_PATH` |
| `backend/services/embedding.py` | Add `BGEEmbeddings` class + `get_multilingual_model()` singleton |
| `backend/services/classifier.py` | Add `detect_language()` using langdetect |
| `backend/services/rag.py` | Add `_vectorstore_es` singleton, `detected_lang` param to `run_rag_query` |
| `backend/routers/query.py` | Call `detect_language()`, pass `detected_lang` to `run_rag_query` |
| `backend/requirements.txt` | Add `langdetect` |
| `ingestion/embedder.py` | Parametric `dimension` in `get_pinecone_index()` |
| `ingestion/pipeline.py` | Add `--lang`, `--index` CLI args; write `source_lang` to chunk metadata |
| `ingestion/create_multilingual_index.py` | New: one-time Pinecone 1024-dim index setup |
| `ingestion/translate_corpus.py` | New: Layer A MT translation EN→ES, writes `es_chunks/corpus_es.jsonl` |
| `ingestion/ingest_es_chunks.py` | New: upsert translated JSONL chunks into multilingual index |
| `evals/build_es_eval.py` | New: translate `eval_set_v2.jsonl` → `ar_agqa_es.jsonl` |
| `evals/ar_agqa_es.jsonl` | New: generated Spanish Q&A benchmark (committed after generation) |
| `.github/workflows/nightly-eval.yml` | Add parallel `eval-es` job |
| `backend/tests/test_f1_lang_routing.py` | New: all F1 backend unit tests |

---

### Task 1: Config + BGE-M3 Multilingual Embedder

**Context:** `backend/services/embedding.py` has one class `MiniLMEmbeddings` wrapping `all-MiniLM-L6-v2` (384-dim). We add a second class `BGEEmbeddings` for `BAAI/bge-m3` (1024-dim). Both use module-level singleton patterns (`_model`, `_multilingual_model`). `backend/config.py` needs two new env vars. No existing tests cover `embedding.py` directly — create the test file fresh.

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/services/embedding.py`
- Create: `backend/tests/test_f1_lang_routing.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_f1_lang_routing.py`:

```python
import sys
from pathlib import Path
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_bge_embeddings_produces_1024_dim(monkeypatch):
    """BGEEmbeddings.embed_query must return a list of 1024 floats."""
    import numpy as np

    fake_vec = np.zeros(1024, dtype="float32")

    class FakeModel:
        def encode(self, texts, normalize_embeddings=True):
            if isinstance(texts, list):
                return np.stack([fake_vec] * len(texts))
            return fake_vec

    import services.embedding as emb_mod
    monkeypatch.setattr(emb_mod, "_multilingual_model", FakeModel())

    from services.embedding import BGEEmbeddings
    bge = BGEEmbeddings()
    result = bge.embed_query("¿Cómo controlo el acaro del arroz?")
    assert len(result) == 1024
    assert all(isinstance(v, float) for v in result)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_f1_lang_routing.py::test_bge_embeddings_produces_1024_dim -v
```
Expected: `ImportError` — `cannot import name 'BGEEmbeddings'`

- [ ] **Step 3: Update `backend/config.py`**

Add after the existing `EMBEDDING_MODEL_PATH` line (line 13):

```python
MULTILINGUAL_EMBEDDING_MODEL_PATH = os.environ.get(
    "MULTILINGUAL_EMBEDDING_MODEL_PATH", "BAAI/bge-m3"
)
PINECONE_MULTILINGUAL_INDEX_NAME = os.environ.get(
    "PINECONE_MULTILINGUAL_INDEX_NAME", "agroar-prod-multilingual"
)
```

- [ ] **Step 4: Replace `backend/services/embedding.py`**

```python
"""Singleton sentence-transformer embedders: MiniLM (EN) and BGE-M3 (multilingual)."""
import os
from sentence_transformers import SentenceTransformer
from langchain_core.embeddings import Embeddings

_model: SentenceTransformer | None = None
_multilingual_model: SentenceTransformer | None = None
MODEL_NAME = os.environ.get("EMBEDDING_MODEL_PATH", "sentence-transformers/all-MiniLM-L6-v2")
MULTILINGUAL_MODEL_NAME = os.environ.get("MULTILINGUAL_EMBEDDING_MODEL_PATH", "BAAI/bge-m3")


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def get_multilingual_model() -> SentenceTransformer:
    global _multilingual_model
    if _multilingual_model is None:
        _multilingual_model = SentenceTransformer(MULTILINGUAL_MODEL_NAME)
    return _multilingual_model


class MiniLMEmbeddings(Embeddings):
    """LangChain-compatible EN embeddings (384-dim, fine-tuned MiniLM v2)."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return get_model().encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return get_model().encode(text, normalize_embeddings=True).tolist()


class BGEEmbeddings(Embeddings):
    """LangChain-compatible multilingual embeddings (1024-dim, BGE-M3)."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return get_multilingual_model().encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return get_multilingual_model().encode(text, normalize_embeddings=True).tolist()
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && pytest tests/test_f1_lang_routing.py::test_bge_embeddings_produces_1024_dim -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/services/embedding.py backend/tests/test_f1_lang_routing.py
git commit -m "feat(f1): add BGEEmbeddings class and multilingual config vars"
```

---

### Task 2: Language Detection Utility

**Context:** Every query must be classified as 'en' or 'es' before RAG routing. `langdetect` is non-deterministic by default — set `DetectorFactory.seed = 0` once at import time. The function must default to `'en'` on any exception (empty text, short text, mixed text all raise `LangDetectException`). `langdetect` goes in `backend/services/classifier.py`, not a new file — the PRD specifies this location.

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/services/classifier.py`
- Modify: `backend/tests/test_f1_lang_routing.py`

- [ ] **Step 1: Add `langdetect` to `backend/requirements.txt`**

Add this line to `backend/requirements.txt`:
```
langdetect==1.0.9
```

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/test_f1_lang_routing.py`:

```python
def test_detect_language_spanish():
    from services.classifier import detect_language
    assert detect_language("¿Cómo controlo el acaro del arroz en Arkansas?") == "es"


def test_detect_language_english():
    from services.classifier import detect_language
    assert detect_language("How do I control blast disease in rice?") == "en"


def test_detect_language_empty_defaults_en():
    from services.classifier import detect_language
    assert detect_language("") == "en"


def test_detect_language_short_text_defaults_en():
    from services.classifier import detect_language
    # Very short text raises LangDetectException — must default to 'en'
    assert detect_language("ok") == "en"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_f1_lang_routing.py -k "test_detect_language" -v
```
Expected: `ImportError: cannot import name 'detect_language' from 'services.classifier'`

- [ ] **Step 4: Update `backend/services/classifier.py`**

Add these imports after the existing `from langchain_core.messages import HumanMessage` line:

```python
from langdetect import detect, LangDetectException
from langdetect import DetectorFactory as _DF
_DF.seed = 0  # deterministic detection across all calls
```

Add this function after the `_FOLLOWUP_WORD_LIMIT = 8` line, before `CLASSIFIER_PROMPT`:

```python
def detect_language(text: str) -> str:
    """Return 'es' if text is Spanish, 'en' for everything else.

    Defaults to 'en' on detection failure (empty, too-short, or ambiguous text).
    """
    if not text or not text.strip():
        return "en"
    try:
        return "es" if detect(text) == "es" else "en"
    except LangDetectException:
        return "en"
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_f1_lang_routing.py -k "test_detect_language" -v
```
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/services/classifier.py backend/tests/test_f1_lang_routing.py
git commit -m "feat(f1): add detect_language() with langdetect, seed=0 for reproducibility"
```

---

### Task 3: Language-Aware RAG Vectorstore Routing

**Context:** `backend/services/rag.py` has a single `_vectorstore: PineconeVectorStore | None = None` singleton (MiniLMEmbeddings → `agroar-prod`). Add a second `_vectorstore_es` singleton (BGEEmbeddings → `agroar-prod-multilingual`). `run_rag_query` gains a `detected_lang: str = "en"` param — when `"es"`, uses `_get_vectorstore_es()`; otherwise uses `_get_vectorstore()`. The ES vectorstore is only instantiated on first Spanish query, so booting the EN path doesn't load BGE-M3 into memory. If the multilingual index doesn't exist yet (no corpus ingested), fall back to the EN vectorstore with a warning log.

**Files:**
- Modify: `backend/services/rag.py`
- Modify: `backend/tests/test_f1_lang_routing.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_f1_lang_routing.py`:

```python
def test_run_rag_query_es_uses_multilingual_vectorstore(monkeypatch):
    """detected_lang='es' → similarity_search called on multilingual vectorstore."""
    import asyncio
    import importlib
    from langchain_core.documents import Document

    rag = importlib.import_module("services.rag")
    calls = []

    class FakeVS:
        def __init__(self, name):
            self._name = name

        def similarity_search(self, query, **kwargs):
            calls.append(self._name)
            return [Document(page_content="test chunk", metadata={"document_title": "T"})]

    class FakeLLM:
        def with_structured_output(self, schema):
            return self

        async def ainvoke(self, messages):
            from models.advisory import AdvisoryResponse, ContextMeta
            return AdvisoryResponse(
                problem_summary="test",
                likely_causes=[],
                recommended_actions=[],
                products_rates=[],
                warnings=[],
                confidence="High",
                citations=[],
                context_meta=ContextMeta(),
            )

    monkeypatch.setattr(rag, "_vectorstore", FakeVS("en"))
    monkeypatch.setattr(rag, "_vectorstore_es", FakeVS("es"))
    monkeypatch.setattr(rag, "_get_llm", lambda: FakeLLM())

    async def fake_get_context(_fips):
        return {"soil": {}, "weather": {}}

    monkeypatch.setattr(rag, "get_context", fake_get_context)

    import services.citation_guard_v2 as cgv2

    async def fake_verify(answer, chunks):
        return {"confidence_score": 0.9, "claim_verification": []}

    monkeypatch.setattr(cgv2, "verify_answer", fake_verify)

    asyncio.run(rag.run_rag_query(
        message="¿Cómo controlo el acaro en arroz?",
        county_fips="05001",
        language="es",
        category="IN_SCOPE_RICE",
        session_history=[],
        detected_lang="es",
    ))

    assert "es" in calls, f"Expected multilingual vectorstore, got calls={calls}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_f1_lang_routing.py::test_run_rag_query_es_uses_multilingual_vectorstore -v
```
Expected: `TypeError: run_rag_query() got an unexpected keyword argument 'detected_lang'`

- [ ] **Step 3: Update `backend/services/rag.py`**

Add `BGEEmbeddings` to the imports at the top (alongside existing `MiniLMEmbeddings` import):

```python
from services.embedding import MiniLMEmbeddings, BGEEmbeddings
```

Add `_vectorstore_es` module-level singleton after `_vectorstore: PineconeVectorStore | None = None`:

```python
_vectorstore_es: PineconeVectorStore | None = None
```

Add `_get_vectorstore_es()` function after the existing `_get_vectorstore()` function:

```python
def _get_vectorstore_es() -> PineconeVectorStore | None:
    """Multilingual vectorstore (BGE-M3, agroar-prod-multilingual). Returns None if unavailable."""
    global _vectorstore_es
    if _vectorstore_es is None:
        try:
            pc = Pinecone(api_key=config.PINECONE_API_KEY)
            index = pc.Index(config.PINECONE_MULTILINGUAL_INDEX_NAME)
            _vectorstore_es = PineconeVectorStore(
                index=index,
                embedding=BGEEmbeddings(),
                text_key="text",
            )
        except Exception:
            logger.warning(
                "Multilingual vectorstore unavailable — falling back to EN index",
                exc_info=True,
            )
            return None
    return _vectorstore_es
```

Update the `run_rag_query` signature to add `detected_lang`:

```python
async def run_rag_query(
    *,
    message: str,
    county_fips: str,
    language: str,
    category: str,
    session_history: list[dict],
    rice_fields: list[dict] | None = None,
    detected_lang: str = "en",
) -> tuple[AdvisoryResponse, list[dict]]:
```

Inside `run_rag_query`, replace the line `vectorstore = _get_vectorstore()` (the line just before `retriever_kwargs = {"k": config.TOP_K_RETRIEVAL}`) with:

```python
    # Route to multilingual index for Spanish queries; fall back to EN if unavailable
    if detected_lang == "es":
        vectorstore = _get_vectorstore_es() or _get_vectorstore()
    else:
        vectorstore = _get_vectorstore()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_f1_lang_routing.py::test_run_rag_query_es_uses_multilingual_vectorstore -v
```
Expected: PASS

- [ ] **Step 5: Run full backend test suite**

```bash
cd backend && pytest tests/ -v --ignore=tests/test_citation_guard_v2.py
```
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add backend/services/rag.py backend/tests/test_f1_lang_routing.py
git commit -m "feat(f1): language-aware RAG routing — ES queries use multilingual vectorstore with EN fallback"
```

---

### Task 4: Wire Language Detection Through Query Router

**Context:** `backend/routers/query.py` currently passes `language = req.language` (the UI toggle value) to `run_rag_query`. We now also call `detect_language(req.message)` after sanitization — this is the true routing signal. Note: `detect_language` is already imported from `services.classifier` alongside `classify_query`. The closure `event_stream()` captures `detected_lang` from the outer `query()` scope.

**Files:**
- Modify: `backend/routers/query.py`
- Modify: `backend/tests/test_f1_lang_routing.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_f1_lang_routing.py`:

```python
def test_query_router_passes_detected_lang_to_rag(monkeypatch):
    """Spanish message → detected_lang='es' forwarded to run_rag_query even if UI lang is 'en'."""
    import asyncio
    import importlib

    query_router = importlib.import_module("routers.query")
    detected_langs_seen = []

    async def fake_classify(_message, **_kwargs):
        return "IN_SCOPE_RICE"

    class FakeResult:
        confidence_score = 0.9
        escalation = None

        def model_dump(self):
            return {"problem_summary": "test"}

    async def fake_run_rag(**kwargs):
        detected_langs_seen.append(kwargs.get("detected_lang"))
        return FakeResult(), []

    monkeypatch.setattr(query_router, "classify_query", fake_classify)
    monkeypatch.setattr(query_router, "run_rag_query", fake_run_rag)
    monkeypatch.setattr(query_router, "save_message", lambda *a, **k: {"id": "x"})
    monkeypatch.setattr(query_router, "get_profile", lambda _: {"county_fips": "05001"})
    monkeypatch.setattr(query_router, "rate_limit_hit", lambda *_: (True, 1))

    req = query_router.QueryRequest(
        message="¿Cómo controlo el acaro del arroz?",
        language="en",  # UI toggle is EN, but message is Spanish
        session_id="s1",
    )
    response = asyncio.run(query_router.query(req, {"sub": "user-id"}))

    async def drain():
        async for _ in response.body_iterator:
            pass

    asyncio.run(drain())

    assert detected_langs_seen == ["es"], f"Expected ['es'], got {detected_langs_seen}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_f1_lang_routing.py::test_query_router_passes_detected_lang_to_rag -v
```
Expected: FAIL — `detected_lang` not present or wrong value.

- [ ] **Step 3: Update `backend/routers/query.py`**

Change the classifier import line from:
```python
from services.classifier import classify_query
```
to:
```python
from services.classifier import classify_query, detect_language
```

After the line `category = await classify_query(req.message, last_category=req.last_category)` inside `query()`, add:

```python
    detected_lang = detect_language(req.message)
```

Inside the `event_stream()` closure, update the `run_rag_query(...)` call to add `detected_lang=detected_lang`:

```python
            result, retrieved_chunks = await run_rag_query(
                message=req.message,
                county_fips=county_fips,
                language=language,
                category=category,
                session_history=req.session_history,
                rice_fields=rice_fields,
                detected_lang=detected_lang,
            )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/test_f1_lang_routing.py::test_query_router_passes_detected_lang_to_rag -v
```
Expected: PASS

- [ ] **Step 5: Run full backend test suite**

```bash
cd backend && pytest tests/ -v --ignore=tests/test_citation_guard_v2.py
```
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/query.py backend/tests/test_f1_lang_routing.py
git commit -m "feat(f1): wire detect_language() through query router to RAG routing"
```

---

### Task 5: Ingestion Pipeline Spanish Support

**Context:** The ingestion pipeline at `ingestion/` runs PDFs through PyMuPDF → chunker → embedder → Pinecone upsert. Three changes needed: (1) `embedder.py` hard-codes `dimension=384` — make it parametric by auto-detecting from the loaded model via `model.get_sentence_embedding_dimension()`; (2) `pipeline.py` needs `--lang` and `--index` flags for native Spanish PDFs (Layers B/C) and must write `source_lang` to chunk metadata; (3) two new scripts: `create_multilingual_index.py` (one-time index setup) and `translate_corpus.py` + `ingest_es_chunks.py` (Layer A MT bootstrap).

**Files:**
- Modify: `ingestion/embedder.py`
- Modify: `ingestion/pipeline.py`
- Create: `ingestion/create_multilingual_index.py`
- Create: `ingestion/translate_corpus.py`
- Create: `ingestion/ingest_es_chunks.py`

- [ ] **Step 1: Update `ingestion/embedder.py` — parametric dimension**

Replace the entire `get_pinecone_index` function:

```python
def get_pinecone_index(api_key: str, index_name: str, dimension: int = 384):
    pc = Pinecone(api_key=api_key)
    existing = [i.name for i in pc.list_indexes()]
    if index_name not in existing:
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(index_name).status["ready"]:
            time.sleep(1)
    return pc.Index(index_name)
```

Replace the `embed_and_upsert` function to auto-detect dimension from the model:

```python
def embed_and_upsert(
    documents: list[Document],
    *,
    api_key: str,
    index_name: str,
    namespace: str,
    model: SentenceTransformer | None = None,
) -> int:
    if not documents:
        return 0

    if model is None:
        model = SentenceTransformer(MODEL_NAME)

    dimension = model.get_sentence_embedding_dimension()
    index = get_pinecone_index(api_key, index_name, dimension=dimension)
    total_upserted = 0

    for i in range(0, len(documents), BATCH_SIZE):
        batch = documents[i: i + BATCH_SIZE]
        texts = [doc.page_content for doc in batch]
        embeddings = model.encode(texts, normalize_embeddings=True).tolist()

        vectors = []
        for doc, emb in zip(batch, embeddings):
            vectors.append({
                "id": doc.metadata["chunk_id"],
                "values": emb,
                "metadata": {**doc.metadata, "text": doc.page_content},
            })

        index.upsert(vectors=vectors, namespace=namespace)
        total_upserted += len(vectors)

    return total_upserted
```

- [ ] **Step 2: Update `ingestion/pipeline.py` — `--lang`, `--index`, `source_lang` metadata**

Update `run_pipeline` signature:

```python
def run_pipeline(
    force_reindex: bool = False,
    source_lang: str = "en",
    index_override: str | None = None,
) -> dict:
```

Inside `run_pipeline`, add `index_name = index_override or PINECONE_INDEX_NAME` as the first line of the function body (before `manifest = load_manifest()`). Then use `index_name` in the `embed_and_upsert` call instead of `PINECONE_INDEX_NAME`:

```python
def run_pipeline(
    force_reindex: bool = False,
    source_lang: str = "en",
    index_override: str | None = None,
) -> dict:
    index_name = index_override or PINECONE_INDEX_NAME
    manifest = load_manifest()
    model = SentenceTransformer(MODEL_NAME)

    pdf_files = sorted(RAW_PDFS_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {RAW_PDFS_DIR}. Add PDFs and re-run.")
        return {"processed": 0, "skipped": 0, "failed": 0, "total_vectors": 0}

    print(f"Found {len(pdf_files)} PDFs.")
    log = {"processed": [], "skipped": [], "failed": []}
    total_vectors = 0

    for pdf_path in pdf_files:
        name = pdf_path.stem
        print(f"\nProcessing: {pdf_path.name}")

        try:
            text = extract_text(str(pdf_path))
            text_hash = _doc_hash(text)

            if not force_reindex and manifest.get(name, {}).get("hash") == text_hash:
                print(f"  Skipped (unchanged)")
                log["skipped"].append(name)
                continue

            tables = extract_tables_as_text(str(pdf_path))
            if tables:
                text += "\n\n" + "\n\n".join(tables)

            crop_type = _infer_crop_type(pdf_path.name)
            docs = chunk_document(
                text,
                document_title=name.replace("_", " ").replace("-", " "),
                source_url=f"file://{pdf_path.resolve()}",
                crop_type=crop_type,
            )
            for doc in docs:
                doc.metadata["source_lang"] = source_lang

            n = embed_and_upsert(
                docs,
                api_key=PINECONE_API_KEY,
                index_name=index_name,
                namespace=crop_type,
                model=model,
            )
            total_vectors += n
            manifest[name] = {"hash": text_hash, "vectors": n, "crop_type": crop_type}
            print(f"  Upserted {n} vectors (namespace: {crop_type}, lang: {source_lang})")
            log["processed"].append({"file": name, "vectors": n, "crop_type": crop_type})

        except Exception as e:
            print(f"  FAILED: {e}")
            log["failed"].append({"file": name, "error": str(e)})

    save_manifest(manifest)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"run_{timestamp}.json"
    summary = {
        "processed": len(log["processed"]),
        "skipped": len(log["skipped"]),
        "failed": len(log["failed"]),
        "total_vectors": total_vectors,
        "details": log,
    }
    with open(log_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(
        f"\nDone. Processed: {summary['processed']}, Skipped: {summary['skipped']}, "
        f"Failed: {summary['failed']}, Total vectors: {total_vectors}"
    )
    print(f"Log: {log_path}")
    return summary
```

Update the `__main__` block at the bottom of `pipeline.py`:

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-index all docs even if unchanged")
    parser.add_argument(
        "--lang", default="en", choices=["en", "es"],
        help="Source language tag written to chunk metadata (default: en)",
    )
    parser.add_argument(
        "--index", default=None,
        help="Override PINECONE_INDEX_NAME env var (e.g. agroar-prod-multilingual)",
    )
    args = parser.parse_args()
    run_pipeline(force_reindex=args.force, source_lang=args.lang, index_override=args.index)
```

- [ ] **Step 3: Create `ingestion/create_multilingual_index.py`**

```python
"""One-time setup: create the agroar-prod-multilingual Pinecone index (1024-dim).

Run once before ingesting any Spanish corpus content:
    python ingestion/create_multilingual_index.py

Set PINECONE_MULTILINGUAL_INDEX_NAME env var to override the default index name.
"""
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from pinecone import Pinecone, ServerlessSpec

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
INDEX_NAME = os.environ.get("PINECONE_MULTILINGUAL_INDEX_NAME", "agroar-prod-multilingual")
DIMENSION = 1024


def create_index() -> None:
    pc = Pinecone(api_key=PINECONE_API_KEY)
    existing = [i.name for i in pc.list_indexes()]
    if INDEX_NAME in existing:
        print(f"Index '{INDEX_NAME}' already exists. Nothing to do.")
        return

    print(f"Creating '{INDEX_NAME}' ({DIMENSION}-dim, cosine, serverless us-east-1)...")
    pc.create_index(
        name=INDEX_NAME,
        dimension=DIMENSION,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    while not pc.describe_index(INDEX_NAME).status["ready"]:
        time.sleep(1)
    print(f"Index '{INDEX_NAME}' ready.")


if __name__ == "__main__":
    create_index()
```

- [ ] **Step 4: Create `ingestion/translate_corpus.py`**

```python
"""Layer A MT bootstrap: translate existing EN corpus chunks to Spanish.

Reads raw PDFs from ingestion/raw_pdfs/, chunks them, translates each chunk with
Helsinki-NLP/opus-mt-en-es, and writes ingestion/es_chunks/corpus_es.jsonl.

Usage:
    python ingestion/translate_corpus.py
    python ingestion/translate_corpus.py --batch-size 32

After translation, ingest with:
    python ingestion/ingest_es_chunks.py
"""
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from extractor import extract_text, extract_tables_as_text
from chunker import chunk_document

RAW_PDFS_DIR = Path(__file__).parent / "raw_pdfs"
ES_CHUNKS_DIR = Path(__file__).parent / "es_chunks"
OUTPUT_PATH = ES_CHUNKS_DIR / "corpus_es.jsonl"
CROP_TYPE_PREFIXES = {"rice", "soybeans", "poultry", "general"}


def _infer_crop_type(filename: str) -> str:
    name = filename.lower()
    for crop in CROP_TYPE_PREFIXES:
        if name.startswith(crop + "_") or name.startswith(crop + "-"):
            return crop
    return "general"


def translate_corpus(batch_size: int = 16) -> int:
    from transformers import pipeline as hf_pipeline

    ES_CHUNKS_DIR.mkdir(exist_ok=True)
    translator = hf_pipeline(
        "translation",
        model="Helsinki-NLP/opus-mt-en-es",
        batch_size=batch_size,
        device=-1,  # CPU; set to 0 for GPU
    )

    pdf_files = sorted(RAW_PDFS_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs in {RAW_PDFS_DIR}")
        return 0

    total = 0
    with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
        for pdf_path in pdf_files:
            print(f"Translating: {pdf_path.name}")
            try:
                text = extract_text(str(pdf_path))
                tables = extract_tables_as_text(str(pdf_path))
                if tables:
                    text += "\n\n" + "\n\n".join(tables)

                name = pdf_path.stem
                crop_type = _infer_crop_type(pdf_path.name)
                docs = chunk_document(
                    text,
                    document_title=name.replace("_", " ").replace("-", " "),
                    source_url=f"file://{pdf_path.resolve()}",
                    crop_type=crop_type,
                )

                texts = [doc.page_content for doc in docs]
                translated_texts = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    results = translator(batch, max_length=512)
                    translated_texts.extend(r["translation_text"] for r in results)

                for doc, es_text in zip(docs, translated_texts):
                    record = {
                        **doc.metadata,
                        "text": es_text,
                        "source_lang": "es",
                        "translation_method": "mt",
                        "source_en_chunk_id": doc.metadata.get("chunk_id", ""),
                    }
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    total += 1

                print(f"  → {len(docs)} chunks translated")
            except Exception as e:
                print(f"  FAILED: {e}")

    print(f"\nWrote {total} Spanish chunks to {OUTPUT_PATH}")
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    translate_corpus(batch_size=args.batch_size)
```

- [ ] **Step 5: Create `ingestion/ingest_es_chunks.py`**

```python
"""Upsert translated ES chunks from ingestion/es_chunks/corpus_es.jsonl into Pinecone.

Run after translate_corpus.py:
    python ingestion/ingest_es_chunks.py

Set PINECONE_MULTILINGUAL_INDEX_NAME to override index name (default: agroar-prod-multilingual).
Uses BAAI/bge-m3 (1024-dim) embeddings.
"""
import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer
from langchain_core.documents import Document

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
INDEX_NAME = os.environ.get("PINECONE_MULTILINGUAL_INDEX_NAME", "agroar-prod-multilingual")
BGE_MODEL_NAME = os.environ.get("MULTILINGUAL_EMBEDDING_MODEL_PATH", "BAAI/bge-m3")
INPUT_PATH = Path(__file__).parent / "es_chunks" / "corpus_es.jsonl"
BATCH_SIZE = 64
DIMENSION = 1024


def _get_or_create_index(pc: Pinecone):
    existing = [i.name for i in pc.list_indexes()]
    if INDEX_NAME not in existing:
        print(f"Creating index '{INDEX_NAME}' ({DIMENSION}-dim)...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        while not pc.describe_index(INDEX_NAME).status["ready"]:
            time.sleep(1)
    return pc.Index(INDEX_NAME)


def ingest_es_chunks() -> int:
    if not INPUT_PATH.exists():
        print(f"Input not found: {INPUT_PATH}. Run translate_corpus.py first.")
        return 0

    rows = []
    with open(INPUT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        print("No chunks in input file.")
        return 0

    print(f"Loading BGE-M3 model: {BGE_MODEL_NAME}")
    model = SentenceTransformer(BGE_MODEL_NAME)
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = _get_or_create_index(pc)

    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        texts = [r["text"] for r in batch]
        embeddings = model.encode(texts, normalize_embeddings=True).tolist()

        vectors = []
        for record, emb in zip(batch, embeddings):
            chunk_id = record.get("chunk_id", f"es_{i}_{len(vectors)}")
            namespace = record.get("crop_type", "general")
            vectors.append({
                "id": chunk_id,
                "values": emb,
                "metadata": {k: v for k, v in record.items() if k != "text"},
            })
            # Upsert per namespace (Pinecone upsert batches must share namespace)
        by_namespace: dict[str, list] = {}
        for vec, record in zip(vectors, batch):
            ns = record.get("crop_type", "general")
            by_namespace.setdefault(ns, []).append(vec)

        for ns, ns_vectors in by_namespace.items():
            index.upsert(vectors=ns_vectors, namespace=ns)
            total += len(ns_vectors)

        print(f"  Upserted batch {i // BATCH_SIZE + 1}: {len(vectors)} vectors")

    print(f"\nTotal upserted: {total} vectors to '{INDEX_NAME}'")
    return total


if __name__ == "__main__":
    ingest_es_chunks()
```

- [ ] **Step 6: Verify scripts are importable**

```bash
cd ingestion && python -c "
import pipeline
import embedder
import create_multilingual_index
import translate_corpus
import ingest_es_chunks
print('All ingestion scripts import OK')
"
```
Expected: `All ingestion scripts import OK` (no ImportError)

- [ ] **Step 7: Commit**

```bash
git add ingestion/embedder.py ingestion/pipeline.py ingestion/create_multilingual_index.py ingestion/translate_corpus.py ingestion/ingest_es_chunks.py
git commit -m "feat(f1): ingestion pipeline — parametric dimension, --lang/--index flags, MT translation + ES upsert scripts"
```

---

### Task 6: AR-AgQA-ES Benchmark + Nightly Eval

**Context:** The eval harness `evals/eval_runner.py` already supports `--eval-set <path>` and reads `EMBEDDING_MODEL_PATH` + `PINECONE_INDEX_NAME` from env vars — so it works for ES eval by setting those env vars. We generate `evals/ar_agqa_es.jsonl` from `eval_set_v2.jsonl` using Helsinki-NLP MT, then add a parallel `eval-es` job to `nightly-eval.yml` that uses `BAAI/bge-m3` and `agroar-prod-multilingual`. The ES job sets `RUN_ANSWER_EVAL: "0"` since the answer eval RAG chain speaks Spanish only after the corpus is ingested (skip for now to keep CI fast).

**Files:**
- Create: `evals/build_es_eval.py`
- Create: `evals/ar_agqa_es.jsonl` (generated, then committed)
- Modify: `.github/workflows/nightly-eval.yml`

- [ ] **Step 1: Create `evals/build_es_eval.py`**

```python
"""Generate evals/ar_agqa_es.jsonl by MT-translating eval_set_v2.jsonl.

Usage:
    python evals/build_es_eval.py
    python evals/build_es_eval.py --input evals/eval_set_v2.jsonl --output evals/ar_agqa_es.jsonl

Schema preserved: {question, gold_chunk, expected_answer} — same as EN eval set.
Extra fields added: source_question_en, translation_method.

After generation, manually review ~30 entries with a bilingual reviewer for accuracy.
"""
import argparse
import json
from pathlib import Path


def build_es_eval(input_path: Path, output_path: Path, batch_size: int = 16) -> int:
    from transformers import pipeline as hf_pipeline

    rows = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    if not rows:
        print("No rows in input file.")
        return 0

    translator = hf_pipeline(
        "translation",
        model="Helsinki-NLP/opus-mt-en-es",
        batch_size=batch_size,
        device=-1,
    )

    questions = [r["question"] for r in rows]
    expected_answers = [r.get("expected_answer", "") for r in rows]

    print(f"Translating {len(rows)} questions...")
    translated_questions = [r["translation_text"] for r in translator(questions, max_length=256)]

    print(f"Translating {len(rows)} expected answers...")
    translated_answers = [r["translation_text"] for r in translator(expected_answers, max_length=512)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as out:
        for row, es_q, es_a in zip(rows, translated_questions, translated_answers):
            record = {
                "question": es_q,
                "gold_chunk": row.get("gold_chunk", ""),
                "expected_answer": es_a,
                "source_question_en": row["question"],
                "translation_method": "mt",
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Wrote {len(rows)} Spanish eval pairs to {output_path}")
    print("Next: manually review ~30 entries with a bilingual reviewer.")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="evals/eval_set_v2.jsonl")
    parser.add_argument("--output", default="evals/ar_agqa_es.jsonl")
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    build_es_eval(Path(args.input), Path(args.output), args.batch_size)
```

- [ ] **Step 2: Run the script to generate `evals/ar_agqa_es.jsonl`**

```bash
python evals/build_es_eval.py
```
Expected output (N = row count of `eval_set_v2.jsonl`):
```
Translating N questions...
Translating N expected answers...
Wrote N Spanish eval pairs to evals/ar_agqa_es.jsonl
Next: manually review ~30 entries with a bilingual reviewer.
```

Verify:
```bash
python -c "
import json
rows = [json.loads(l) for l in open('evals/ar_agqa_es.jsonl')]
print(f'{len(rows)} rows. First question: {rows[0][\"question\"][:80]}')
assert 'source_question_en' in rows[0]
print('Schema OK')
"
```
Expected: row count printed, first question in Spanish, `Schema OK`.

- [ ] **Step 3: Add parallel `eval-es` job to `.github/workflows/nightly-eval.yml`**

Append the following second job block after the closing of the existing `eval:` job (after the last `retention-days: 30` line):

```yaml

  eval-es:
    name: Run retrieval eval on Spanish corpus
    runs-on: ubuntu-latest
    timeout-minutes: 20

    env:
      EVAL_WRITE_TO_DB: "1"
      RUN_ANSWER_EVAL: "0"
      EMBEDDING_MODEL_PATH: BAAI/bge-m3
      PINECONE_API_KEY: ${{ secrets.PINECONE_API_KEY }}
      PINECONE_INDEX_NAME: ${{ secrets.PINECONE_MULTILINGUAL_INDEX_NAME }}
      SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
      SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
      GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
      GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
      UPSTASH_REDIS_REST_URL: ${{ secrets.UPSTASH_REDIS_REST_URL }}
      UPSTASH_REDIS_REST_TOKEN: ${{ secrets.UPSTASH_REDIS_REST_TOKEN }}
      SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY }}
      SUPABASE_JWT_SECRET: ${{ secrets.SUPABASE_JWT_SECRET }}

    steps:
      - name: Check out repo
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: |
            evals/requirements.txt
            backend/requirements.txt

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r evals/requirements.txt
          pip install -r backend/requirements.txt

      - name: Run Spanish retrieval eval
        run: |
          python evals/eval_runner.py --eval-set evals/ar_agqa_es.jsonl

      - name: Upload ES eval artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: eval-es-results-${{ github.run_id }}
          path: evals/results/eval_*.json
          retention-days: 30
```

**After committing:** Add `PINECONE_MULTILINGUAL_INDEX_NAME` secret in GitHub → Settings → Secrets → Actions. Value: `agroar-prod-multilingual`.

- [ ] **Step 4: Verify workflow YAML is valid**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/nightly-eval.yml')); print('YAML OK')"
```
Expected: `YAML OK`

- [ ] **Step 5: Commit**

```bash
git add evals/build_es_eval.py evals/ar_agqa_es.jsonl .github/workflows/nightly-eval.yml
git commit -m "feat(f1): AR-AgQA-ES benchmark script, generated eval set, parallel ES nightly eval CI job"
```

---

### Task 7: Final Verification + Frontend Lint

**Context:** The frontend already sends `language` in the SSE body (`useSSEQuery.js` line 43 — verified in codebase reading). No frontend code changes needed for F1. This task runs final test + lint to confirm clean state.

**Files:**
- No changes — verification only

- [ ] **Step 1: Verify `language` is in the SSE request body**

```bash
grep -n "language" frontend/src/hooks/useSSEQuery.js
```
Expected: line with `language,` inside the `body: JSON.stringify({...})` block.

- [ ] **Step 2: Frontend lint**

```bash
cd frontend && npm run lint
```
Expected: 0 errors.

- [ ] **Step 3: Full backend test suite**

```bash
cd backend && pytest tests/ -v --ignore=tests/test_citation_guard_v2.py
```
Expected: All tests pass, including all `test_f1_lang_routing.py` tests.

- [ ] **Step 4: Count F1 tests**

```bash
cd backend && pytest tests/test_f1_lang_routing.py -v --collect-only
```
Expected: 7 tests collected (1 BGE dim test + 4 detect_language tests + 1 ES vectorstore test + 1 query router test).

- [ ] **Step 5: Final commit**

```bash
git commit --allow-empty -m "test(f1): verified frontend language pass-through, lint clean, all backend tests passing"
```

---

## Post-Implementation Ops Checklist (manual, outside codebase)

These steps require human action after all code is merged:

1. **Create Pinecone multilingual index** (once, in production):
   ```bash
   PINECONE_API_KEY=<prod_key> python ingestion/create_multilingual_index.py
   ```

2. **Layer A — translate EN corpus**:
   ```bash
   python ingestion/translate_corpus.py
   ```

3. **Layer A — ingest ES chunks**:
   ```bash
   PINECONE_API_KEY=<prod_key> python ingestion/ingest_es_chunks.py
   ```

4. **Layers B/C — ingest native Spanish PDFs** (place PDFs in `ingestion/raw_pdfs/`):
   ```bash
   EMBEDDING_MODEL_PATH=BAAI/bge-m3 \
   python ingestion/pipeline.py --lang es --index agroar-prod-multilingual
   ```

5. **GitHub Actions secret**: Add `PINECONE_MULTILINGUAL_INDEX_NAME=agroar-prod-multilingual` in repo Settings → Secrets → Actions.

6. **Manual review**: Review 30 entries in `evals/ar_agqa_es.jsonl` with a bilingual reviewer. Correct translations and re-run the eval to get baseline MRR@5.
