# Rice Gold-Label Curation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce `evals/eval_set_v2_clean_rice.jsonl` — the rice gold labels re-pointed off the non-answer-bearing "br wells … research studies" yearly-volume TOCs onto the dedicated topical rice docs, so the rice correctness/faithfulness headline measures the pipeline instead of the gold quality.

**Architecture:** Eval-only **data** curation. A new pure-helper module `evals/rice_gold_curation.py` (flag → candidate-search → apply → audit), driven by a human-reviewed decisions table. Draws replacement gold from `ingestion/en_chunks/corpus_v3.jsonl` (the v3 corpus that backs the live `agroar-prod-gte-v3` index) by an independent keyword search — deliberately NOT the prod gte embedder, and blind to any eval dump — so the post-curation headline stays NIW/arXiv-honest (no train-on-test circularity). Touches no `backend/`, `frontend/`, or retrieval pipeline.

**Tech Stack:** Python 3.13, pytest. No new dependencies, no LLM, no network for Tasks 1–7. Re-measure (Task 8) reuses the existing `evals/answer_eval_full.py` + `evals/ragas_eval.py`.

**Spec:** `docs/superpowers/specs/completed/2026-06-12-rice-gold-curation-design.md`.

---

## Handoff (read first — this plan is meant to be built in a FRESH session)

No prior conversation context is required. Everything a cold session needs:

- **Branch:** `feat/rice-gold-curation`. The spec and this plan are committed here, **NOT on `main`**. Run `git switch feat/rice-gold-curation` before starting. Eval-only changes → pushing this branch triggers **no** HF/Vercel deploy (deploy Actions watch `backend/**` and `frontend/`).
- **Why this exists:** the 2026-06-13 rice diagnosis (`docs/superpowers/2026-06-13-rice-diagnosis-findings.md`) found rice correctness 18% is *substantially an eval-measurement artifact* — `GOLD_ARTIFACT + EVAL_MISLABEL = 58%` of rice failures, `TRUE_RETRIEVAL = 0`. **70 of 111 rice rows** (63%) have gold pointing at a yearly "br wells arkansas rice research studies" volume the judge itself calls a "table of contents" / "list of academic citations" with "no recommendations." A correct how-to answer cannot score `corr=1.0` against a non-answer-bearing gold passage. This is a DATA fix, not a pipeline lever — it will not change `rag.py` or any prompt.
- **The honesty crux (read the spec §2):** replacement gold is chosen by independent topical correctness, never by what the model retrieved. Candidate search uses keyword/term overlap over v3 `source_text` (a *different* mechanism than the gte-dense prod retrieval) and is run blind to eval dumps. This avoids the train-on-test inflation that invalidated the MRR 0.65 figure (see `memory/project_eval_contamination.md`).
- **Cost map:** Tasks 1–7 are **$0** — pure helpers + a deterministic draft + a human review + file writes + asserts. **Task 8 is the only token-spend** (a gen re-run n=40 + optional RAGAS matrix). **STOP and get explicit Taiwo OK before Task 8**, even mid-build (Taiwo is cost-averse — `memory/feedback_avoid_token_cost.md`).
- **The one human-in-the-loop step is Task 6** (review the draft audit, supply overrides). A cold agent should pause there and surface the draft audit table to Taiwo, not invent agronomy silently.
- **Run all commands from the repo root.** Tests: `python -m pytest evals/...`. The module is pure Python; it reads `evals/eval_set_v2_clean.jsonl` and `ingestion/en_chunks/corpus_v3.jsonl` by repo-root-relative path.
- **Env state:** no new packages. `corpus_v3.jsonl` is present (41 MB, 21,065 chunks, rice 16,392) at `ingestion/en_chunks/corpus_v3.jsonl`; its chunk schema keys are `{doc_id, document_title, source_url, crop_type, doc_type, page_start, page_end, section_heading, subsection_heading, chunk_id, parent_section_id, section_index, chunk_index, retrieval_header, retrieval_text, namespace, source_text}`.
- **Definition of done for the build session:** Tasks 1–7 implemented, committed per-task, full pytest suite green ($0), `evals/eval_set_v2_clean_rice.jsonl` written + validated, audit doc committed. Task 8 left pending Taiwo's cost OK; once run, results go in `PROGRESS.md`.

---

## File Structure

- **Create** `evals/rice_gold_curation.py` — the curation module: `flag_yearly_volume_gold`, `load_corpus_v3`, `candidate_chunks`, `apply_curation`, `write_audit`, plus a `main()` that generates the draft decisions + audit. All pure (no LLM/network).
- **Create** `evals/test_rice_gold_curation.py` — pytest for every pure helper, seeded in-memory fixtures, no file/network dependency.
- **Create** `evals/rice_curation_decisions.json` — the decisions table (draft generated in Task 5, human-finalized in Task 6). One object per changed query: `{"query", "action": "repoint"|"drop", "new_chunk_id"|null, "reason"}`.
- **Create** `evals/eval_set_v2_clean_rice.jsonl` — the curated output (Task 7). Same 5-key schema as the input.
- **Create** `docs/superpowers/2026-06-12-rice-gold-curation-audit.md` — the human-review audit table (Task 5 draft, Task 6 finalized).

> **Originals preserved:** `evals/eval_set_v2.jsonl` (pristine) and `evals/eval_set_v2_clean.jsonl` (current canonical) are READ-ONLY in this plan — never edited.

---

## Task 1: Module skeleton + `flag_yearly_volume_gold`

**Files:**
- Create: `evals/rice_gold_curation.py`
- Test: `evals/test_rice_gold_curation.py`

The flag is deterministic: a rice row is a yearly-volume artifact iff its gold `document_title` matches the "br wells … research studies" signature. Verified live: this matches exactly 70 of 111 rice rows, and correctly leaves the answer-bearing "2026 arkansas rice management guide" and "2021 performance trials" docs unflagged.

- [ ] **Step 1: Write the failing test**

Create `evals/test_rice_gold_curation.py`:

```python
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))

from rice_gold_curation import flag_yearly_volume_gold


def test_flag_matches_br_wells_research_volumes_only():
    rows = [
        {"query": "q1", "namespace": "rice",
         "document_title": "rice 2019 br wells arkansas rice research studies"},
        {"query": "q2", "namespace": "rice",
         "document_title": "rice 2023 br wells arkansas rice research studies"},
        # answer-bearing docs that contain a year but are NOT TOC volumes -> keep
        {"query": "q3", "namespace": "rice",
         "document_title": "rice 2026 arkansas rice management guide"},
        {"query": "q4", "namespace": "rice",
         "document_title": "rice arkansas rice production handbook"},
        # non-rice row -> never flagged
        {"query": "q5", "namespace": "soybeans",
         "document_title": "soybeans 2020 br wells research studies"},
    ]
    flagged = flag_yearly_volume_gold(rows)
    titles = {r["query"] for r in flagged}
    assert titles == {"q1", "q2"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/test_rice_gold_curation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rice_gold_curation'`.

- [ ] **Step 3: Create the module + flag helper**

Create `evals/rice_gold_curation.py`:

```python
"""OFFLINE rice gold-label curation (eval-only, $0 for the pure helpers).

Re-points rice gold off the non-answer-bearing "br wells ... research studies"
yearly-volume TOCs onto dedicated topical rice docs drawn from corpus_v3, by an
INDEPENDENT keyword search (not the prod gte embedder, blind to eval dumps) so
the post-curation rice headline stays honest. See the design spec:
docs/superpowers/specs/completed/2026-06-12-rice-gold-curation-design.md

NEVER imported by backend/rag.py or the request path.
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CLEAN_SET = Path(__file__).parent / "eval_set_v2_clean.jsonl"
CORPUS_V3 = REPO_ROOT / "ingestion" / "en_chunks" / "corpus_v3.jsonl"

# The non-answer-bearing yearly research-volume signature. Targets the "br wells
# ... research studies" compilations specifically; deliberately does NOT match
# answer-bearing docs that merely contain a year (management guide, perf trials).
_YEARLY_VOLUME_RE = re.compile(r"br wells.*research stud", re.IGNORECASE)


def flag_yearly_volume_gold(rows: list[dict]) -> list[dict]:
    """Return the rice rows whose gold document_title is a yearly-volume TOC."""
    return [
        r for r in rows
        if r.get("namespace") == "rice"
        and _YEARLY_VOLUME_RE.search(r.get("document_title", ""))
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest evals/test_rice_gold_curation.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/rice_gold_curation.py evals/test_rice_gold_curation.py
git commit -m "feat(evals): flag yearly-volume rice gold (curation Task 1)"
```

---

## Task 2: `load_corpus_v3` + `candidate_chunks` (independent keyword search)

**Files:**
- Modify: `evals/rice_gold_curation.py`
- Test: `evals/test_rice_gold_curation.py`

`candidate_chunks` surfaces replacement-gold candidates by term overlap between the question and each v3 chunk's `source_text`, restricted to rice chunks and EXCLUDING other yearly-volume TOCs (so we never re-point one TOC onto another). It is the independent mechanism (keyword, not gte-dense) the spec's circularity guard requires. It only *surfaces* candidates; the human pick happens in Task 6.

- [ ] **Step 1: Write the failing test**

Append to `evals/test_rice_gold_curation.py`:

```python
from rice_gold_curation import candidate_chunks


def test_candidate_chunks_ranks_topical_overlap_and_excludes_toc():
    corpus = [
        {"chunk_id": "c_pot", "namespace": "rice",
         "document_title": "rice ch 9 soil fertility",
         "source_text": "Potassium deficiency in rice reduces yield; apply potash "
                          "based on soil test potassium levels."},
        {"chunk_id": "c_water", "namespace": "rice",
         "document_title": "rice ch 10 water management",
         "source_text": "Maintain a consistent flood depth for water-seeded rice."},
        # a TOC volume must be excluded even if terms overlap
        {"chunk_id": "c_toc", "namespace": "rice",
         "document_title": "rice 2019 br wells arkansas rice research studies",
         "source_text": "potassium potassium potassium table of contents"},
        # non-rice chunk must be excluded
        {"chunk_id": "c_soy", "namespace": "soybeans",
         "document_title": "soybeans fertility",
         "source_text": "potassium for soybeans"},
    ]
    cands = candidate_chunks("how much potassium potash for my rice", corpus, k=3)
    ids = [c["chunk_id"] for c in cands]
    # top candidate is the topical potassium chunk; TOC + non-rice excluded
    assert ids[0] == "c_pot"
    assert "c_toc" not in ids
    assert "c_soy" not in ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/test_rice_gold_curation.py::test_candidate_chunks_ranks_topical_overlap_and_excludes_toc -v`
Expected: FAIL — `ImportError: cannot import name 'candidate_chunks'`.

- [ ] **Step 3: Implement the loader + search**

Add to `evals/rice_gold_curation.py`:

```python
_WORD_RE = re.compile(r"[a-z]{3,}")  # 3+ letter lowercase tokens
# Generic agronomy/question stopwords that don't discriminate topic.
_STOP = {
    "the", "and", "for", "with", "are", "can", "you", "your", "how", "what",
    "much", "many", "should", "would", "could", "rice", "field", "fields",
    "crop", "crops", "farm", "use", "using", "get", "got", "put", "have",
    "this", "that", "from", "out", "about", "into", "they", "them", "some",
    "best", "good", "more", "less", "when", "where", "which", "will", "does",
}


def _tokens(text: str) -> set:
    return {w for w in _WORD_RE.findall((text or "").lower()) if w not in _STOP}


def load_corpus_v3(path=CORPUS_V3) -> list[dict]:
    """Load the v3 corpus (one JSON object per line)."""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def candidate_chunks(question: str, corpus: list[dict], k: int = 10) -> list[dict]:
    """Rank rice corpus chunks by term overlap with the question, EXCLUDING the
    yearly-volume TOCs. Independent of the prod gte retrieval (keyword only).

    Returns up to k dicts: {chunk_id, document_title, source_text, score}.
    """
    q = _tokens(question)
    scored = []
    for c in corpus:
        if c.get("namespace") != "rice":
            continue
        if _YEARLY_VOLUME_RE.search(c.get("document_title", "")):
            continue
        overlap = len(q & _tokens(c.get("source_text", "")))
        if overlap:
            scored.append((overlap, c))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [
        {"chunk_id": c["chunk_id"], "document_title": c["document_title"],
         "source_text": c["source_text"], "score": s}
        for s, c in scored[:k]
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest evals/test_rice_gold_curation.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/rice_gold_curation.py evals/test_rice_gold_curation.py
git commit -m "feat(evals): independent keyword candidate search over corpus_v3 (curation Task 2)"
```

---

## Task 3: `apply_curation` (drop + re-point from the decisions table)

**Files:**
- Modify: `evals/rice_gold_curation.py`
- Test: `evals/test_rice_gold_curation.py`

`apply_curation` is the pure transform: given the clean rows, the v3 corpus (as a `chunk_id → chunk` index), and a decisions list, it DROPs flagged queries, RE-POINTs gold (new `chunk_id` + `chunk_text=source_text` + `document_title` looked up from v3), and passes every other row through unchanged. Keeping decisions as data (not hardcoded edits) makes this deterministic and testable.

- [ ] **Step 1: Write the failing test**

Append to `evals/test_rice_gold_curation.py`:

```python
from rice_gold_curation import apply_curation


def test_apply_curation_drops_repoints_and_passes_through():
    rows = [
        {"query": "q_drop", "namespace": "rice", "chunk_id": "old1",
         "chunk_text": "old text 1", "document_title": "rice 2019 br wells arkansas rice research studies"},
        {"query": "q_repoint", "namespace": "rice", "chunk_id": "old2",
         "chunk_text": "old text 2", "document_title": "rice 2023 br wells arkansas rice research studies"},
        {"query": "q_keep_rice", "namespace": "rice", "chunk_id": "old3",
         "chunk_text": "keep me", "document_title": "rice arkansas rice production handbook"},
        {"query": "q_soy", "namespace": "soybeans", "chunk_id": "old4",
         "chunk_text": "soy", "document_title": "soybeans doc"},
    ]
    corpus_index = {
        "new_pot": {"chunk_id": "new_pot", "document_title": "rice ch 9 soil fertility",
                    "source_text": "potassium guidance text"},
    }
    decisions = [
        {"query": "q_drop", "action": "drop", "new_chunk_id": None, "reason": "corn question"},
        {"query": "q_repoint", "action": "repoint", "new_chunk_id": "new_pot", "reason": "potassium doc"},
    ]
    out = apply_curation(rows, corpus_index, decisions)

    queries = [r["query"] for r in out]
    assert "q_drop" not in queries                 # dropped
    assert queries == ["q_repoint", "q_keep_rice", "q_soy"]  # order preserved, drop removed

    repointed = next(r for r in out if r["query"] == "q_repoint")
    assert repointed["chunk_id"] == "new_pot"
    assert repointed["chunk_text"] == "potassium guidance text"
    assert repointed["document_title"] == "rice ch 9 soil fertility"
    assert set(repointed.keys()) == {"query", "namespace", "chunk_id", "chunk_text", "document_title"}

    # untouched rows pass through byte-for-byte
    assert next(r for r in out if r["query"] == "q_keep_rice")["chunk_text"] == "keep me"
    assert next(r for r in out if r["query"] == "q_soy")["document_title"] == "soybeans doc"


def test_apply_curation_raises_on_unknown_repoint_chunk():
    rows = [{"query": "q", "namespace": "rice", "chunk_id": "o",
             "chunk_text": "t", "document_title": "rice 2019 br wells arkansas rice research studies"}]
    decisions = [{"query": "q", "action": "repoint", "new_chunk_id": "missing", "reason": "x"}]
    try:
        apply_curation(rows, {}, decisions)
        assert False, "expected KeyError for unknown chunk_id"
    except KeyError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/test_rice_gold_curation.py -k apply_curation -v`
Expected: FAIL — `ImportError: cannot import name 'apply_curation'`.

- [ ] **Step 3: Implement `apply_curation`**

Add to `evals/rice_gold_curation.py`:

```python
def apply_curation(rows: list[dict], corpus_index: dict, decisions: list[dict]) -> list[dict]:
    """Apply the decisions table to the clean rows.

    rows          : the full eval set (all namespaces), order preserved.
    corpus_index  : {chunk_id -> v3 chunk dict} for repoint lookups.
    decisions     : [{query, action: 'drop'|'repoint', new_chunk_id, reason}, ...]

    Returns a new list: dropped queries removed, repointed gold replaced from v3,
    every other row passed through unchanged. Raises KeyError if a repoint names a
    chunk_id absent from corpus_index.
    """
    by_query = {d["query"]: d for d in decisions}
    out = []
    for r in rows:
        d = by_query.get(r["query"])
        if d is None:
            out.append(r)
            continue
        if d["action"] == "drop":
            continue
        if d["action"] == "repoint":
            chunk = corpus_index[d["new_chunk_id"]]  # KeyError if unknown
            out.append({
                "query": r["query"],
                "namespace": r["namespace"],
                "chunk_id": chunk["chunk_id"],
                "chunk_text": chunk["source_text"],
                "document_title": chunk["document_title"],
            })
            continue
        raise ValueError(f"unknown action {d['action']!r} for query {r['query']!r}")
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest evals/test_rice_gold_curation.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/rice_gold_curation.py evals/test_rice_gold_curation.py
git commit -m "feat(evals): apply_curation drop+repoint transform (curation Task 3)"
```

---

## Task 4: `write_audit` (human-review markdown table)

**Files:**
- Modify: `evals/rice_gold_curation.py`
- Test: `evals/test_rice_gold_curation.py`

The audit is the human artifact Taiwo spot-checks in Task 6 — one row per change, showing the old gold title, the chosen new gold title + chunk_id, and the reason.

- [ ] **Step 1: Write the failing test**

Append to `evals/test_rice_gold_curation.py`:

```python
from rice_gold_curation import write_audit


def test_write_audit_renders_one_row_per_change():
    rows = [
        {"query": "how much potassium for rice", "namespace": "rice", "chunk_id": "old2",
         "document_title": "rice 2023 br wells arkansas rice research studies"},
        {"query": "corn nitrogen question", "namespace": "rice", "chunk_id": "old1",
         "document_title": "rice 2019 br wells arkansas rice research studies"},
    ]
    corpus_index = {
        "new_pot": {"chunk_id": "new_pot", "document_title": "rice ch 9 soil fertility",
                    "source_text": "potassium guidance"},
    }
    decisions = [
        {"query": "how much potassium for rice", "action": "repoint",
         "new_chunk_id": "new_pot", "reason": "dedicated potassium doc"},
        {"query": "corn nitrogen question", "action": "drop",
         "new_chunk_id": None, "reason": "corn, not rice"},
    ]
    md = write_audit(rows, corpus_index, decisions)
    assert "how much potassium for rice" in md
    assert "rice 2023 br wells" in md                 # old title shown
    assert "rice ch 9 soil fertility" in md           # new title shown
    assert "new_pot" in md                            # new chunk_id shown
    assert "drop" in md.lower()                       # drop action shown
    assert "dedicated potassium doc" in md            # reason shown
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/test_rice_gold_curation.py::test_write_audit_renders_one_row_per_change -v`
Expected: FAIL — `ImportError: cannot import name 'write_audit'`.

- [ ] **Step 3: Implement `write_audit`**

Add to `evals/rice_gold_curation.py`:

```python
def write_audit(rows: list[dict], corpus_index: dict, decisions: list[dict]) -> str:
    """Render a markdown audit table: one row per decision.

    Columns: query | action | old_gold_title | new_gold_title | new_chunk_id | reason.
    """
    by_query = {r["query"]: r for r in rows}
    lines = [
        "# Rice Gold Curation — Audit",
        "",
        "Review each row. For a wrong re-point, edit the corresponding entry in",
        "`evals/rice_curation_decisions.json` (change `new_chunk_id` or set",
        "`action` to `drop`), then re-run Task 7.",
        "",
        "| query | action | old gold title | new gold title | new chunk_id | reason |",
        "|---|---|---|---|---|---|",
    ]
    for d in decisions:
        old_row = by_query.get(d["query"], {})
        old_title = old_row.get("document_title", "?")
        if d["action"] == "repoint":
            chunk = corpus_index.get(d["new_chunk_id"], {})
            new_title = chunk.get("document_title", "?")
        else:
            new_title = "—"
        q = d["query"].replace("|", "\\|")
        lines.append(
            f"| {q[:70]} | {d['action']} | {old_title[:50]} | {new_title[:50]} "
            f"| {d.get('new_chunk_id') or '—'} | {d.get('reason','')[:60]} |"
        )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest evals/test_rice_gold_curation.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/rice_gold_curation.py evals/test_rice_gold_curation.py
git commit -m "feat(evals): write_audit markdown table (curation Task 4)"
```

---

## Task 5: Generate the DRAFT decisions + audit ($0)

**Files:**
- Modify: `evals/rice_gold_curation.py` (add `main()`)
- Create (generated): `evals/rice_curation_decisions.json`, `docs/superpowers/2026-06-12-rice-gold-curation-audit.md`

`main()` wires the helpers into a draft: load the clean set + v3 corpus, flag the 70 yearly-volume rows, and for each propose `repoint` to the top `candidate_chunks` hit (top-1 by keyword overlap). It seeds the two known wrong-crop drops (the corn-nitrogen and soybean-variety items the diagnosis found, identified by substring so the worker doesn't need their exact text). The draft is deterministic and reproducible; the human pass (Task 6) corrects it.

- [ ] **Step 1: Add `main()`**

Add to `evals/rice_gold_curation.py`:

```python
DECISIONS_PATH = Path(__file__).parent / "rice_curation_decisions.json"
AUDIT_PATH = REPO_ROOT / "docs" / "superpowers" / "2026-06-12-rice-gold-curation-audit.md"

# Wrong-crop items to DROP outright (substring-matched against the query so we
# don't depend on exact wording). From the rice diagnosis EVAL_MISLABEL bucket:
# a corn-nitrogen question and a soybean-variety question sitting in rice.
_DROP_SUBSTRINGS = [
    "planting soybeans later than usual",   # soybean-variety question (#10)
]
# NOTE: the corn-nitrogen mislabel (#9) is ambiguous by title alone; it is left
# for the Task 6 human pass to confirm/drop. Do not guess it here.


def _load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_draft_decisions(rows: list[dict], corpus: list[dict]) -> list[dict]:
    """Deterministic draft: drop known wrong-crop items, repoint each flagged
    yearly-volume row to its top keyword candidate. Human-reviewed in Task 6."""
    decisions = []
    flagged = flag_yearly_volume_gold(rows)
    flagged_queries = {r["query"] for r in flagged}
    for r in rows:
        if r["query"] not in flagged_queries:
            continue
        if any(s in r["query"].lower() for s in _DROP_SUBSTRINGS):
            decisions.append({"query": r["query"], "action": "drop",
                              "new_chunk_id": None, "reason": "wrong-crop (soybean) in rice namespace"})
            continue
        cands = candidate_chunks(r["query"], corpus, k=5)
        if not cands:
            decisions.append({"query": r["query"], "action": "drop",
                              "new_chunk_id": None, "reason": "no topical rice candidate found"})
            continue
        top = cands[0]
        decisions.append({"query": r["query"], "action": "repoint",
                          "new_chunk_id": top["chunk_id"],
                          "reason": f"keyword top-1: {top['document_title'][:40]} (score {top['score']})"})
    return decisions


def main():
    rows = _load_jsonl(CLEAN_SET)
    corpus = load_corpus_v3()
    corpus_index = {c["chunk_id"]: c for c in corpus}
    decisions = build_draft_decisions(rows, corpus)
    with open(DECISIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(decisions, f, indent=2)
    audit = write_audit(rows, corpus_index, decisions)
    with open(AUDIT_PATH, "w", encoding="utf-8") as f:
        f.write(audit)
    n_drop = sum(1 for d in decisions if d["action"] == "drop")
    n_repoint = sum(1 for d in decisions if d["action"] == "repoint")
    print(f"draft decisions: {len(decisions)} ({n_repoint} repoint, {n_drop} drop)")
    print(f"  -> {DECISIONS_PATH}")
    print(f"  -> {AUDIT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate the draft ($0, no LLM)**

Run: `python evals/rice_gold_curation.py`
Expected: `draft decisions: 70 (69 repoint, 1 drop)` (70 flagged rows: 1 known soybean drop + 69 repoint proposals), and the two files written.

- [ ] **Step 3: Run the full test suite (still green)**

Run: `python -m pytest evals/test_rice_gold_curation.py -v`
Expected: all PASS (5 passed).

- [ ] **Step 4: Commit the draft**

```bash
git add evals/rice_gold_curation.py evals/rice_curation_decisions.json docs/superpowers/2026-06-12-rice-gold-curation-audit.md
git commit -m "feat(evals): generate draft rice-curation decisions + audit (curation Task 5)"
```

---

## Task 6: HUMAN REVIEW GATE — finalize the decisions table

**Files:**
- Modify (by hand, reviewed): `evals/rice_curation_decisions.json`
- Regenerate: `docs/superpowers/2026-06-12-rice-gold-curation-audit.md`

> **This is the one human-in-the-loop step. Do NOT silently accept the keyword top-1 picks — surface the draft audit to Taiwo and incorporate corrections.**

- [ ] **Step 1: Present the draft audit to Taiwo**

Open `docs/superpowers/2026-06-12-rice-gold-curation-audit.md` and show Taiwo the table (or the rows with low keyword score / suspicious new-title). Each repoint must be an agronomically-correct topical doc for that question; each drop must be genuinely off-crop. Flag for Taiwo any row where the keyword top-1 looks wrong (e.g. a water-management chunk picked for a fertility question).

- [ ] **Step 2: Apply corrections to the decisions JSON**

For each row Taiwo corrects: edit that object in `evals/rice_curation_decisions.json` — change `new_chunk_id` to the agronomically-correct v3 chunk (find candidates with `python -c "import sys; sys.path.insert(0,'evals'); from rice_gold_curation import load_corpus_v3, candidate_chunks; [print(c['score'], c['chunk_id'], c['document_title']) for c in candidate_chunks('<the question>', load_corpus_v3(), k=10)]"`), or set `action` to `drop` with a reason. Confirm or drop the corn-nitrogen item here.

- [ ] **Step 3: Regenerate the audit from the finalized decisions**

Add a tiny regen path — run:
```bash
python -c "import sys; sys.path.insert(0,'evals'); import json; from rice_gold_curation import _load_jsonl, load_corpus_v3, write_audit, CLEAN_SET, DECISIONS_PATH, AUDIT_PATH; rows=_load_jsonl(CLEAN_SET); ci={c['chunk_id']:c for c in load_corpus_v3()}; dec=json.load(open(DECISIONS_PATH,encoding='utf-8')); open(AUDIT_PATH,'w',encoding='utf-8').write(write_audit(rows,ci,dec)); print('audit regenerated')"
```
Expected: `audit regenerated`.

- [ ] **Step 4: Commit the finalized decisions + audit**

```bash
git add evals/rice_curation_decisions.json docs/superpowers/2026-06-12-rice-gold-curation-audit.md
git commit -m "chore(evals): finalize human-reviewed rice-curation decisions (curation Task 6)"
```

---

## Task 7: Apply + validate + write `eval_set_v2_clean_rice.jsonl` ($0)

**Files:**
- Modify: `evals/rice_gold_curation.py` (add `build_curated_set` + `validate`)
- Test: `evals/test_rice_gold_curation.py`
- Create (generated): `evals/eval_set_v2_clean_rice.jsonl`

- [ ] **Step 1: Write the failing test for validation**

Append to `evals/test_rice_gold_curation.py`:

```python
from rice_gold_curation import validate_curated


def test_validate_curated_catches_toc_and_count_errors():
    clean = [
        {"query": "a", "namespace": "rice", "chunk_id": "o", "chunk_text": "t",
         "document_title": "rice 2019 br wells arkansas rice research studies"},
        {"query": "b", "namespace": "soybeans", "chunk_id": "o2", "chunk_text": "t2",
         "document_title": "soy"},
    ]
    # good: 'a' repointed off the TOC, 'b' untouched, 1 drop -> but here 0 drops, count must match
    good = [
        {"query": "a", "namespace": "rice", "chunk_id": "n", "chunk_text": "potash",
         "document_title": "rice ch 9 soil fertility"},
        {"query": "b", "namespace": "soybeans", "chunk_id": "o2", "chunk_text": "t2",
         "document_title": "soy"},
    ]
    validate_curated(clean, good, dropped=0)  # no raise

    # bad: still points at a br-wells TOC
    bad_toc = [dict(good[0], document_title="rice 2023 br wells arkansas rice research studies"), good[1]]
    try:
        validate_curated(clean, bad_toc, dropped=0)
        assert False, "expected ValueError for residual TOC gold"
    except ValueError:
        pass

    # bad: row count doesn't match clean - dropped
    try:
        validate_curated(clean, good, dropped=1)
        assert False, "expected ValueError for count mismatch"
    except ValueError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/test_rice_gold_curation.py -k validate -v`
Expected: FAIL — `ImportError: cannot import name 'validate_curated'`.

- [ ] **Step 3: Implement `validate_curated` + `build_curated_set`**

Add to `evals/rice_gold_curation.py`:

```python
def validate_curated(clean_rows: list[dict], curated_rows: list[dict], dropped: int) -> None:
    """Assert the curated set is well-formed. Raises ValueError on any violation."""
    # row math
    if len(curated_rows) != len(clean_rows) - dropped:
        raise ValueError(
            f"row count {len(curated_rows)} != clean {len(clean_rows)} - dropped {dropped}")
    # no residual yearly-volume gold in rice
    for r in curated_rows:
        if r.get("namespace") == "rice" and _YEARLY_VOLUME_RE.search(r.get("document_title", "")):
            raise ValueError(f"residual TOC gold for query {r['query']!r}")
        if set(r.keys()) != {"query", "namespace", "chunk_id", "chunk_text", "document_title"}:
            raise ValueError(f"unexpected schema for query {r['query']!r}: {sorted(r.keys())}")
    # non-rice rows unchanged in count
    n_nonrice_clean = sum(1 for r in clean_rows if r.get("namespace") != "rice")
    n_nonrice_cur = sum(1 for r in curated_rows if r.get("namespace") != "rice")
    if n_nonrice_clean != n_nonrice_cur:
        raise ValueError(f"non-rice rows changed: {n_nonrice_clean} -> {n_nonrice_cur}")


def build_curated_set(clean_path=CLEAN_SET, decisions_path=DECISIONS_PATH,
                      out_path=None) -> dict:
    """Apply the finalized decisions, validate, and write the curated set.

    Returns a summary dict. Asserts via validate_curated before writing.
    """
    out_path = out_path or (Path(__file__).parent / "eval_set_v2_clean_rice.jsonl")
    rows = _load_jsonl(clean_path)
    corpus_index = {c["chunk_id"]: c for c in load_corpus_v3()}
    with open(decisions_path, encoding="utf-8") as f:
        decisions = json.load(f)
    # every repoint chunk_id must exist in v3
    for d in decisions:
        if d["action"] == "repoint" and d["new_chunk_id"] not in corpus_index:
            raise KeyError(f"repoint chunk_id {d['new_chunk_id']!r} absent from corpus_v3")
    dropped = sum(1 for d in decisions if d["action"] == "drop")
    curated = apply_curation(rows, corpus_index, decisions)
    validate_curated(rows, curated, dropped)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in curated:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"in": len(rows), "out": len(curated), "dropped": dropped,
            "repointed": sum(1 for d in decisions if d["action"] == "repoint"),
            "path": str(out_path)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest evals/test_rice_gold_curation.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Build the curated set from the finalized decisions ($0)**

Run:
```bash
python -c "import sys; sys.path.insert(0,'evals'); from rice_gold_curation import build_curated_set; print(build_curated_set())"
```
Expected: a summary like `{'in': 198, 'out': 197, 'dropped': 1, 'repointed': 69, 'path': '.../eval_set_v2_clean_rice.jsonl'}` (exact counts depend on Task 6 drops). No `ValueError`/`KeyError` = validation passed.

- [ ] **Step 6: Sanity-check the output ($0)**

Run:
```bash
python -c "import json; r=[json.loads(l) for l in open('evals/eval_set_v2_clean_rice.jsonl',encoding='utf-8')]; rice=[x for x in r if x['namespace']=='rice']; toc=[x for x in rice if 'br wells' in x['document_title'].lower()]; print('rows',len(r),'rice',len(rice),'residual TOC golds',len(toc))"
```
Expected: `residual TOC golds 0`.

- [ ] **Step 7: Commit**

```bash
git add evals/rice_gold_curation.py evals/test_rice_gold_curation.py evals/eval_set_v2_clean_rice.jsonl
git commit -m "feat(evals): build+validate curated rice gold set (curation Task 7)"
```

---

## Task 8: Re-measure (MANUAL, cost-gated — STOP for OK)

**This task spends tokens. Per the cost rule, get explicit Taiwo OK before running either command.**

- [ ] **Step 1: State the cost estimate and get Taiwo's OK**

A gen re-run of n=40 (DeepInfra 70B + Gemini judge) gives the new honest rice corr/faith headline; the optional RAGAS re-run un-provisions rice `context_recall`. Same per-run cost as the prior eval/RAGAS runs. Present this; do not proceed until approved.

- [ ] **Step 2: Headline re-run on the curated set (after OK)**

Run (matches the B1-on baseline arm):
```bash
python evals/answer_eval_full.py --provider deepinfra --judge-provider gemini \
  --eval-set evals/eval_set_v2_clean_rice.jsonl --sample 40 --seed 7 \
  --dump evals/_capture_rice_curated.jsonl
```
Expected: a `=== PER-NAMESPACE BREAKDOWN ===` with a rice corr materially above the pre-curation 18–21% if the artifact diagnosis was right. Record the rice row.

- [ ] **Step 3: (Optional) RAGAS re-run to un-provision rice context_recall (after OK)**

Run:
```bash
python evals/ragas_eval.py --dump evals/_capture_rice_curated.jsonl \
  --eval-set evals/eval_set_v2_clean_rice.jsonl --confirm-cost
```
Expected: the matrix with rice `context_recall` now non-zero (gold is answer-bearing v3 chunks that string-match retrieved context).

- [ ] **Step 4: Record results + gitignore large artifacts**

Add `evals/_capture_rice_curated.jsonl` to `.gitignore` (under the eval-artifacts block). Update `PROGRESS.md` with the new rice headline + interpretation (note whether the artifact hypothesis held). Then:
```bash
git add PROGRESS.md .gitignore
git commit -m "docs(progress): rice gold curation re-measure results"
```

---

## Self-Review (completed)

- **Spec coverage:** §1 inputs/outputs → Task 1 paths + Task 7 output file. §2 flow (flag→drop→repoint→audit→write) → Tasks 1,3,5,7 (flag), 3/5 (drop+repoint), 4/5 (audit), 7 (write). §2 circularity guard (keyword search, exclude TOCs, blind to dump) → Task 2 `candidate_chunks`. §3 four units → Tasks 1–4 exactly (`flag_yearly_volume_gold`, `candidate_chunks`, `apply_curation`, `write_audit`) + decisions-as-data. §4 validation asserts → Task 7 `validate_curated` (existence checked in `build_curated_set`, TOC-moved + row-math + schema in `validate_curated`). §5 paid re-measure gate → Task 8 (`--confirm-cost`, STOP for OK). §6 scope guard (rice only, no pipeline) → no task touches `backend/`. All covered.
- **Placeholder scan:** no TBD/TODO; every code step has complete code; every command states expected output. Task 6 is intentionally human-driven but gives the exact edit + the candidate-search one-liner.
- **Type consistency:** `flag_yearly_volume_gold(rows)→list` (T1) feeds `build_draft_decisions` (T5). `candidate_chunks(question, corpus, k)→[{chunk_id,document_title,source_text,score}]` (T2) → consumed in T5 `top["chunk_id"]`. `apply_curation(rows, corpus_index, decisions)` (T3) ← `build_curated_set` (T7) with `corpus_index={chunk_id:chunk}`. `write_audit(rows, corpus_index, decisions)` (T4) ← T5 `main` + T6 regen. `validate_curated(clean, curated, dropped)` (T7) raises `ValueError`. Decisions object shape `{query, action, new_chunk_id, reason}` consistent across T3/T4/T5/T7. `_YEARLY_VOLUME_RE` single source for flag + candidate-exclude + validate. Consistent.
