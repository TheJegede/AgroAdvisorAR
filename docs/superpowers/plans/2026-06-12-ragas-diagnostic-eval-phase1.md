# RAGAS Diagnostic Eval — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone, offline RAGAS scorer (`evals/ragas_eval.py`) that completes the retrieval×generation measurement matrix — `faithfulness`, `answer_relevancy`, `context_precision` (reference-free), `context_recall` (gold-chunk reference) — per crop, segmented by guard-suppression, on the existing held-out query set.

**Architecture:** Two units. (1) A small capture extension to `evals/answer_eval_full.py` that persists the advisory `answer` prose + untruncated retrieved `contexts` into its `--dump` (the existing dump lacks both — RAGAS needs them). (2) A new standalone `evals/ragas_eval.py` that reads that dump, joins gold `chunk_text` from `eval_set_v2_clean.jsonl` as `reference_contexts`, builds a RAGAS `EvaluationDataset`, scores it with a Gemini-2.5-flash judge + local gte embedder, and prints a per-crop / segmented report. **Eval-only — never imported by `rag.py`, never in the request path, guard/`confidence_score` untouched.**

**Tech Stack:** Python 3.13, pytest, `ragas==0.4.3` (eval-only dep), `langchain-google-genai` (Gemini judge), `backend/services/embedding.MiniLMEmbeddings` (local gte, $0). RAGAS LangChain wrappers: `LangchainLLMWrapper`, `LangchainEmbeddingsWrapper`.

**Spec:** `docs/superpowers/specs/2026-06-12-ragas-diagnostic-eval-design.md`.

---

## Handoff (read first — this plan is meant to be built in a FRESH session)

Standard workflow: plans are developed in one session and built in another (`/build`), so this section carries everything a cold session needs. No prior conversation context is required.

- **Branch:** `feat/ragas-diagnostic-eval`. The spec, this plan, and a `plans/` → `plans/completed/` reorg are committed here — **NOT on `main`**. `git switch feat/ragas-diagnostic-eval` before starting.
- **Where the "why" lives:** the spec (link above) for design rationale + the 3 pending issues; `PROGRESS.md` top "RESUME HERE" block for one-screen orientation. Read the spec once before Task 1.
- **What this is:** a DIAGNOSTIC instrument (completes the retrieval×generation metric matrix), **NOT a lever** — it will not raise the faithfulness (~≤67%) / correctness (~≤37%) ceilings, only explain them. Eval-only: nothing here imports `rag.py` or touches the production guard / `confidence_score`.
- **Cost discipline (hard rule, user is cost-averse):** Tasks 0–6 cost **$0** — pure helpers, judge/embedder mocked, no live LLM. **Task 7 is the only token-spending step** (a gen re-run of n=40 + a few hundred gemini-2.5-flash calls). **STOP and get explicit user OK before running Task 7**, even mid-build.
- **Env state (Task 0 front-run):** `ragas==0.4.3` + `rapidfuzz` were already `pip install`-ed into the local env during planning, and verified to coexist cleanly with `langchain 1.2.x` / `langchain-core 1.4.x` (no downgrade). `pip install -r evals/requirements-ragas.txt` is therefore idempotent locally. A benign `s3fs==2025.3.2` vs `fsspec` pin warning appears on install — ignore it (`s3fs` still imports, unused by evals).
- **Run all commands from the repo root.** Tests: `python -m pytest evals/...`. The eval scripts add `backend/` to `sys.path` themselves.
- **Definition of done for the build session:** Tasks 0–6 implemented, committed per-task, full pytest suite green ($0). Task 7 left pending the user's cost OK; once run, its results go in `PROGRESS.md`.

---

## File Structure

- **Create** `evals/requirements-ragas.txt` — eval-only dependency pin (ragas). NOT added to `backend/requirements.txt` (keeps the HF Docker image lean).
- **Create** `evals/ragas_eval.py` — the standalone scorer. Pure helpers (dump load, gold join, sample build, aggregation) + a thin `main()` that does the cost-incurring RAGAS run behind a confirmation gate.
- **Create** `evals/test_ragas_eval.py` — pytest for every pure helper, judge + embedder mocked, no live LLM.
- **Modify** `evals/answer_eval_full.py` — add a `_capture_fields(adv, chunks)` helper and include its output in the `evaluate()` return dict (so `--dump` carries `answer` + `contexts`).
- **Create** `evals/test_answer_eval_capture.py` — pytest for `_capture_fields` (pure, no LLM).

> **Note on existing dumps:** `evals/_out_clean_indepjudge_b1on.jsonl` (the B1 baseline) was produced before this extension and has neither `answer` nor `contexts`. Phase 1 produces a **fresh** capture-enabled dump (Task 5); it does not retrofit old dumps.

---

## Task 0: RAGAS dependency + import smoke test

**Files:**
- Create: `evals/requirements-ragas.txt`

- [ ] **Step 1: Create the eval-only requirements file**

Create `evals/requirements-ragas.txt`:

```
# RAGAS diagnostic eval — EVAL-ONLY dependency.
# Do NOT add to backend/requirements.txt: ragas is never imported by the
# backend/request path, and keeping it out preserves the lean HF Docker image.
# Verified clean against langchain 1.2.x / langchain-core 1.4.x (no downgrade).
# Known benign side-effect: ragas bumps fsspec, which trips an s3fs==2025.3.2
# pin warning; s3fs still imports fine and is unused by evals.
ragas==0.4.3
# Required by NonLLMContextRecall (string-distance recall) — NOT pulled in by
# ragas itself; without it the metric raises at runtime.
rapidfuzz
```

- [ ] **Step 2: Install + import smoke test (no LLM, $0)**

Run:
```bash
pip install -r evals/requirements-ragas.txt
python -c "from ragas import SingleTurnSample, EvaluationDataset, evaluate; from ragas.metrics import Faithfulness, ResponseRelevancy, LLMContextPrecisionWithoutReference, NonLLMContextRecall; from ragas.llms import LangchainLLMWrapper; from ragas.embeddings import LangchainEmbeddingsWrapper; ms=[Faithfulness(), ResponseRelevancy(), LLMContextPrecisionWithoutReference(), NonLLMContextRecall()]; print('ragas OK; metric names:', [m.name for m in ms])"
```
Expected: `ragas OK; metric names: ['faithfulness', 'answer_relevancy', 'llm_context_precision_without_reference', 'non_llm_context_recall']` (DeprecationWarnings about `ragas.metrics` vs `ragas.metrics.collections` are fine for 0.4.3; instantiating `NonLLMContextRecall` confirms `rapidfuzz` is present).

- [ ] **Step 3: Commit**

```bash
git add evals/requirements-ragas.txt
git commit -m "build(evals): add ragas as eval-only dependency (Phase 1 Task 0)"
```

---

## Task 1: Capture extension — persist `answer` + `contexts` in the dump

**Files:**
- Modify: `evals/answer_eval_full.py` (add helper near `_is_suppressed`, ~line 48; use in `evaluate()` return dict, ~line 196-212)
- Test: `evals/test_answer_eval_capture.py`

Context: in `evaluate()`, `adv` is the advisory dict and `chunks` is the list of retrieved chunk dicts (each has `document_title` + `snippet`, per `faithfulness()` at line 153-156). `_summarize_advisory(adv)` (imported from `judge`) returns the advisory as a flat prose string. We add a pure helper so it is unit-testable without the live RAG chain.

- [ ] **Step 1: Write the failing test**

Create `evals/test_answer_eval_capture.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from answer_eval_full import _capture_fields


def test_capture_fields_extracts_answer_and_full_contexts():
    adv = {
        "problem_summary": "Rice sheath blight risk is high.",
        "recommended_actions": ["Scout fields", "Apply fungicide if threshold met"],
    }
    chunks = [
        {"document_title": "MP154", "snippet": "Apply azoxystrobin at 0.2 lb ai/acre."},
        {"document_title": "FSA2042", "snippet": "Sheath blight thrives in dense canopies."},
    ]
    out = _capture_fields(adv, chunks)

    # answer is the flattened advisory prose (non-empty string)
    assert isinstance(out["answer"], str) and out["answer"].strip()
    # contexts is the list of retrieved chunk snippets, untruncated, in order
    assert out["contexts"] == [
        "Apply azoxystrobin at 0.2 lb ai/acre.",
        "Sheath blight thrives in dense canopies.",
    ]


def test_capture_fields_handles_empty_chunks():
    out = _capture_fields({"problem_summary": "x"}, [])
    assert out["contexts"] == []
    assert isinstance(out["answer"], str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/test_answer_eval_capture.py -v`
Expected: FAIL — `ImportError: cannot import name '_capture_fields'`.

- [ ] **Step 3: Add the helper**

In `evals/answer_eval_full.py`, immediately after the `_is_suppressed` function (after line 47), add:

```python
def _capture_fields(adv: dict, chunks: list[dict]) -> dict:
    """RAGAS-capture fields for the --dump record: the advisory as flat prose
    (the 'answer' RAGAS scores) and the FULL retrieved chunk snippets (the
    'contexts'), untruncated. Pure — no LLM, safe to unit-test."""
    return {
        "answer": _summarize_advisory(adv),
        "contexts": [(c.get("snippet") or "") for c in chunks],
    }
```

- [ ] **Step 4: Wire it into the `evaluate()` return dict**

In `evals/answer_eval_full.py`, in the dict returned by `evaluate()` (currently lines 196-212), add the captured fields. Change the `return {` block so it includes them — insert these two keys just before the closing `}` (after the `chunk_snippets` line):

```python
        "chunk_snippets": [(c.get("snippet") or "")[:500] for c in chunks],
        **_capture_fields(adv, chunks),
    }
```

(`_capture_fields` returns `answer` + `contexts`; spreading keeps the existing keys and adds the two RAGAS needs.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest evals/test_answer_eval_capture.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add evals/answer_eval_full.py evals/test_answer_eval_capture.py
git commit -m "feat(evals): capture answer+contexts in dump for RAGAS (Phase 1 Task 1)"
```

---

## Task 2: `ragas_eval.py` — dump load + gold reference-context join

**Files:**
- Create: `evals/ragas_eval.py`
- Test: `evals/test_ragas_eval.py`

- [ ] **Step 1: Write the failing test**

Create `evals/test_ragas_eval.py`:

```python
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent))

from ragas_eval import load_dump, load_gold_reference_contexts


def _write_jsonl(tmp_path, name, rows):
    p = tmp_path / name
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def test_load_dump_reads_records(tmp_path):
    dump = _write_jsonl(tmp_path, "dump.jsonl", [
        {"query": "q1", "namespace": "rice", "suppressed": False,
         "answer": "a1", "contexts": ["c1", "c2"]},
    ])
    recs = load_dump(dump)
    assert len(recs) == 1
    assert recs[0]["answer"] == "a1"
    assert recs[0]["contexts"] == ["c1", "c2"]


def test_gold_reference_contexts_groups_chunks_by_query(tmp_path):
    gold = _write_jsonl(tmp_path, "gold.jsonl", [
        {"query": "q1", "chunk_text": "gold-a", "namespace": "rice"},
        {"query": "q1", "chunk_text": "gold-b", "namespace": "rice"},
        {"query": "q2", "chunk_text": "gold-c", "namespace": "soybeans"},
    ])
    m = load_gold_reference_contexts(gold)
    assert m["q1"] == ["gold-a", "gold-b"]
    assert m["q2"] == ["gold-c"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/test_ragas_eval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ragas_eval'`.

- [ ] **Step 3: Create `ragas_eval.py` with the two loaders**

Create `evals/ragas_eval.py`:

```python
"""Standalone OFFLINE RAGAS diagnostic eval.

Completes the retrieval x generation measurement matrix on the held-out set:
  faithfulness, answer_relevancy        (generation, reference-free)
  context_precision (reference-free)    (retrieval)
  context_recall (gold-chunk reference) (retrieval; rice = provisional)

Consumes a capture-enabled dump from answer_eval_full.py (--dump, with `answer`
+ `contexts`) and joins gold chunk_text from eval_set_v2_clean.jsonl as
reference_contexts. EVAL-ONLY: never imported by rag.py / the request path.

Run (cost-incurring — see cost gate in main()):
  python evals/ragas_eval.py --dump evals/_capture_b1on.jsonl
"""
import json
from collections import defaultdict
from pathlib import Path


def load_dump(path) -> list[dict]:
    """Read the capture-enabled answer_eval_full dump (one JSON object/line)."""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_gold_reference_contexts(eval_set_path) -> dict:
    """Map query -> [gold chunk_text, ...] from eval_set_v2_clean.jsonl.

    The clean eval set is a *retrieval* gold (query, chunk_id, chunk_text,
    document_title, namespace) with possibly multiple gold chunks per query.
    These serve as RAGAS `reference_contexts` for NonLLMContextRecall.
    """
    out = defaultdict(list)
    with open(eval_set_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            text = row.get("chunk_text")
            if text:
                out[row["query"]].append(text)
    return dict(out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest evals/test_ragas_eval.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/ragas_eval.py evals/test_ragas_eval.py
git commit -m "feat(evals): ragas_eval dump+gold loaders (Phase 1 Task 2)"
```

---

## Task 3: Build RAGAS samples from dump + gold

**Files:**
- Modify: `evals/ragas_eval.py`
- Test: `evals/test_ragas_eval.py`

Context: a RAGAS `SingleTurnSample` carries `user_input`, `response`,
`retrieved_contexts`, `reference_contexts` (verified fields on the 0.4.3 model).
We build one per dump record, attaching `reference_contexts` from the gold map
(empty list when a query has no gold — those rows still score the reference-free
metrics). We keep `namespace` + `suppressed` alongside for aggregation.

- [ ] **Step 1: Write the failing test**

Append to `evals/test_ragas_eval.py`:

```python
from ragas_eval import build_samples


def test_build_samples_pairs_dump_with_gold_and_metadata():
    dump = [
        {"query": "q1", "namespace": "rice", "suppressed": False,
         "answer": "a1", "contexts": ["c1", "c2"]},
        {"query": "q2", "namespace": "soybeans", "suppressed": True,
         "answer": "a2", "contexts": ["c3"]},
    ]
    gold = {"q1": ["gold-a", "gold-b"]}  # q2 has no gold

    samples, meta = build_samples(dump, gold)

    assert len(samples) == 2
    # sample 0
    assert samples[0].user_input == "q1"
    assert samples[0].response == "a1"
    assert samples[0].retrieved_contexts == ["c1", "c2"]
    assert samples[0].reference_contexts == ["gold-a", "gold-b"]
    # sample 1 — no gold -> empty reference_contexts (reference-free metrics still run)
    assert samples[1].reference_contexts == []
    # metadata aligned by index for aggregation
    assert meta[0] == {"namespace": "rice", "suppressed": False}
    assert meta[1] == {"namespace": "soybeans", "suppressed": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/test_ragas_eval.py::test_build_samples_pairs_dump_with_gold_and_metadata -v`
Expected: FAIL — `ImportError: cannot import name 'build_samples'`.

- [ ] **Step 3: Implement `build_samples`**

Add to `evals/ragas_eval.py` (after the loaders):

```python
from ragas import SingleTurnSample


def build_samples(dump_records: list[dict], gold_map: dict) -> tuple[list, list]:
    """Build (SingleTurnSamples, metadata) aligned by index.

    metadata[i] = {"namespace", "suppressed"} for per-crop / per-suppressed
    aggregation, since RAGAS results don't carry our domain fields.
    """
    samples, meta = [], []
    for r in dump_records:
        samples.append(SingleTurnSample(
            user_input=r["query"],
            response=r.get("answer") or "",
            retrieved_contexts=list(r.get("contexts") or []),
            reference_contexts=list(gold_map.get(r["query"], [])),
        ))
        meta.append({
            "namespace": r.get("namespace"),
            "suppressed": bool(r.get("suppressed")),
        })
    return samples, meta
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest evals/test_ragas_eval.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/ragas_eval.py evals/test_ragas_eval.py
git commit -m "feat(evals): build RAGAS SingleTurnSamples from dump+gold (Phase 1 Task 3)"
```

---

## Task 4: Aggregation — per-crop, per-suppressed, rice-provisional flag

**Files:**
- Modify: `evals/ragas_eval.py`
- Test: `evals/test_ragas_eval.py`

Context: after a RAGAS run we have, per row, a dict of metric_name -> score plus
the aligned metadata. `aggregate_scores` groups by namespace (crop) and by the
`suppressed` flag, means each metric over non-None scores, and marks the rice
`context_recall` cell provisional (contaminated gold). It is generic over the
metric-name list so it does not hard-code RAGAS column strings.

- [ ] **Step 1: Write the failing test**

Append to `evals/test_ragas_eval.py`:

```python
from ragas_eval import aggregate_scores

METRICS = ["faithfulness", "answer_relevancy",
           "llm_context_precision_without_reference", "non_llm_context_recall"]


def test_aggregate_means_per_crop_and_flags_rice_recall_provisional():
    rows = [
        {"namespace": "rice", "suppressed": False,
         "faithfulness": 1.0, "answer_relevancy": 0.8,
         "llm_context_precision_without_reference": 0.5,
         "non_llm_context_recall": 0.4},
        {"namespace": "rice", "suppressed": True,
         "faithfulness": 0.0, "answer_relevancy": 0.6,
         "llm_context_precision_without_reference": 0.5,
         "non_llm_context_recall": 0.6},
        {"namespace": "soybeans", "suppressed": False,
         "faithfulness": 0.5, "answer_relevancy": 1.0,
         "llm_context_precision_without_reference": 1.0,
         "non_llm_context_recall": 0.8},
    ]
    report = aggregate_scores(rows, METRICS)

    # per-crop means
    rice = report["by_crop"]["rice"]
    assert rice["count"] == 2
    assert rice["faithfulness"] == 0.5            # (1.0 + 0.0) / 2
    assert rice["answer_relevancy"] == 0.7        # (0.8 + 0.6) / 2
    soy = report["by_crop"]["soybeans"]
    assert soy["faithfulness"] == 0.5

    # overall
    assert report["overall"]["count"] == 3

    # by suppressed flag
    assert report["by_suppressed"][False]["count"] == 2
    assert report["by_suppressed"][True]["count"] == 1

    # rice context_recall flagged provisional (contaminated gold); others not
    assert report["by_crop"]["rice"]["non_llm_context_recall_provisional"] is True
    assert report["by_crop"]["soybeans"]["non_llm_context_recall_provisional"] is False


def test_aggregate_ignores_none_scores_in_means():
    rows = [
        {"namespace": "poultry", "suppressed": False,
         "faithfulness": 1.0, "answer_relevancy": None,
         "llm_context_precision_without_reference": None,
         "non_llm_context_recall": None},
        {"namespace": "poultry", "suppressed": False,
         "faithfulness": 0.0, "answer_relevancy": 0.5,
         "llm_context_precision_without_reference": None,
         "non_llm_context_recall": None},
    ]
    report = aggregate_scores(rows, METRICS)
    p = report["by_crop"]["poultry"]
    assert p["faithfulness"] == 0.5      # (1.0 + 0.0)/2
    assert p["answer_relevancy"] == 0.5  # only the one non-None value
    assert p["llm_context_precision_without_reference"] is None  # all None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/test_ragas_eval.py -k aggregate -v`
Expected: FAIL — `ImportError: cannot import name 'aggregate_scores'`.

- [ ] **Step 3: Implement `aggregate_scores`**

Add to `evals/ragas_eval.py`:

```python
# Reference-based metric(s) whose rice numbers are provisional until Phase 2
# (rice gold labels are contaminated — see spec §3).
_PROVISIONAL_FOR_RICE = {"non_llm_context_recall"}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _summarize_group(rows: list[dict], metric_keys: list[str], crop=None) -> dict:
    out = {"count": len(rows)}
    for k in metric_keys:
        out[k] = _mean([r.get(k) for r in rows])
    if crop is not None:
        for k in _PROVISIONAL_FOR_RICE:
            out[f"{k}_provisional"] = (crop == "rice")
    return out


def aggregate_scores(rows: list[dict], metric_keys: list[str]) -> dict:
    """Group per-row RAGAS scores into a report: overall, per-crop (namespace),
    and per-suppressed-flag. Rice reference-based cells marked provisional."""
    by_crop = defaultdict(list)
    by_supp = defaultdict(list)
    for r in rows:
        by_crop[r.get("namespace")].append(r)
        by_supp[bool(r.get("suppressed"))].append(r)

    return {
        "overall": _summarize_group(rows, metric_keys),
        "by_crop": {c: _summarize_group(g, metric_keys, crop=c)
                    for c, g in sorted(by_crop.items(), key=lambda kv: str(kv[0]))},
        "by_suppressed": {s: _summarize_group(g, metric_keys)
                          for s, g in by_supp.items()},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest evals/test_ragas_eval.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/ragas_eval.py evals/test_ragas_eval.py
git commit -m "feat(evals): per-crop/suppressed RAGAS aggregation + rice provisional flag (Phase 1 Task 4)"
```

---

## Task 5: Report formatting

**Files:**
- Modify: `evals/ragas_eval.py`
- Test: `evals/test_ragas_eval.py`

- [ ] **Step 1: Write the failing test**

Append to `evals/test_ragas_eval.py`:

```python
from ragas_eval import format_report


def test_format_report_renders_crops_and_provisional_marker():
    report = {
        "overall": {"count": 3, "faithfulness": 0.5, "answer_relevancy": 0.7,
                    "llm_context_precision_without_reference": 0.66,
                    "non_llm_context_recall": 0.6},
        "by_crop": {
            "rice": {"count": 2, "faithfulness": 0.5, "answer_relevancy": 0.7,
                     "llm_context_precision_without_reference": 0.5,
                     "non_llm_context_recall": 0.5,
                     "non_llm_context_recall_provisional": True},
        },
        "by_suppressed": {
            False: {"count": 2, "faithfulness": 1.0, "answer_relevancy": 0.9,
                    "llm_context_precision_without_reference": 0.8,
                    "non_llm_context_recall": 0.7},
        },
    }
    text = format_report(report,
                         ["faithfulness", "answer_relevancy",
                          "llm_context_precision_without_reference",
                          "non_llm_context_recall"])
    assert "OVERALL" in text
    assert "rice" in text
    # provisional rice recall cell is marked
    assert "provisional" in text.lower()
    # suppressed segmentation present
    assert "suppressed" in text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest evals/test_ragas_eval.py::test_format_report_renders_crops_and_provisional_marker -v`
Expected: FAIL — `ImportError: cannot import name 'format_report'`.

- [ ] **Step 3: Implement `format_report`**

Add to `evals/ragas_eval.py`:

```python
def _fmt(x):
    return " n/a" if x is None else f"{x:.2f}"


def format_report(report: dict, metric_keys: list[str]) -> str:
    lines = []
    header = f"{'group':>20} {'n':>3} " + " ".join(f"{k[:14]:>14}" for k in metric_keys)

    def row(label, d):
        cells = []
        for k in metric_keys:
            val = _fmt(d.get(k))
            if d.get(f"{k}_provisional"):
                val += "*"
            cells.append(f"{val:>14}")
        lines.append(f"{label:>20} {d.get('count', 0):>3} " + " ".join(cells))

    lines.append("=== RAGAS DIAGNOSTIC MATRIX ===")
    lines.append(header)
    row("OVERALL", report["overall"])
    lines.append("--- by crop ---")
    for crop, d in report["by_crop"].items():
        row(str(crop), d)
    lines.append("--- by suppressed ---")
    for flag, d in report["by_suppressed"].items():
        row(f"suppressed={flag}", d)
    lines.append("* = provisional (contaminated rice gold; fixed in Phase 2)")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest evals/test_ragas_eval.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/ragas_eval.py evals/test_ragas_eval.py
git commit -m "feat(evals): RAGAS report formatting (Phase 1 Task 5)"
```

---

## Task 6: Wire the RAGAS run in `main()` (cost-gated)

**Files:**
- Modify: `evals/ragas_eval.py`

Context: this is the only code that spends tokens, so it lives behind an
explicit `--confirm-cost` flag (the run aborts without it and prints the
estimate). The judge is Gemini-2.5-flash; the embedder is the local gte model.
The metric column names come from each metric's `.name`, so the aggregation/report
key list is derived at runtime (no hard-coded RAGAS strings). No unit test — this
path requires live LLM calls; the pure helpers it calls are already tested.

- [ ] **Step 1: Add the runner + CLI**

Add to `evals/ragas_eval.py`:

```python
import argparse
import os
import sys

# Make backend importable for the local gte embedder.
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


def _build_llm_and_embeddings():
    """Gemini-2.5-flash judge + local gte embedder, wrapped for RAGAS."""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    from langchain_google_genai import ChatGoogleGenerativeAI
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from services.embedding import MiniLMEmbeddings  # local gte, $0

    judge = ChatGoogleGenerativeAI(
        model=os.environ.get("CONTAINMENT_JUDGE_MODEL", "gemini-2.5-flash"),
        google_api_key=os.environ["GOOGLE_API_KEY"],
        temperature=0,
    )
    return (LangchainLLMWrapper(judge),
            LangchainEmbeddingsWrapper(MiniLMEmbeddings()))


def run(dump_path, eval_set_path):
    """Score a capture-enabled dump with the 4-metric matrix. Spends Gemini tokens."""
    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import (
        Faithfulness, ResponseRelevancy,
        LLMContextPrecisionWithoutReference, NonLLMContextRecall,
    )

    dump = load_dump(dump_path)
    gold = load_gold_reference_contexts(eval_set_path)
    samples, meta = build_samples(dump, gold)

    metrics = [
        Faithfulness(),
        ResponseRelevancy(),
        LLMContextPrecisionWithoutReference(),
        NonLLMContextRecall(),
    ]
    metric_keys = [m.name for m in metrics]

    llm, embeddings = _build_llm_and_embeddings()
    result = evaluate(
        dataset=EvaluationDataset(samples=samples),
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
    )

    df = result.to_pandas()
    rows = []
    for i, m in enumerate(meta):
        row = {"namespace": m["namespace"], "suppressed": m["suppressed"]}
        for k in metric_keys:
            val = df[k].iloc[i] if k in df.columns else None
            # RAGAS uses NaN for unscored cells; normalize to None.
            row[k] = None if val is None or (isinstance(val, float) and val != val) else float(val)
        rows.append(row)

    report = aggregate_scores(rows, metric_keys)
    print(format_report(report, metric_keys))
    return report


_COST_NOTE = """\
COST GATE — this run spends Gemini-2.5-flash tokens.
Estimate: ~n items x (faithfulness ~2 calls + answer_relevancy ~1 + context_precision
~1/retrieved-context). For n=40 with ~5 contexts/item this is on the order of a few
hundred gemini-2.5-flash calls (cheap, but non-zero). NonLLMContextRecall uses string
similarity only ($0). Embeddings are local gte ($0).
Re-run with --confirm-cost to proceed."""


def main():
    ap = argparse.ArgumentParser(description="Offline RAGAS diagnostic eval.")
    ap.add_argument("--dump", type=Path, required=True,
                    help="capture-enabled dump from answer_eval_full.py --dump")
    ap.add_argument("--eval-set", type=Path,
                    default=Path(__file__).parent / "eval_set_v2_clean.jsonl",
                    help="gold retrieval set (reference_contexts for context_recall)")
    ap.add_argument("--confirm-cost", action="store_true",
                    help="acknowledge token cost and run (otherwise prints estimate and exits)")
    args = ap.parse_args()

    if not args.confirm_cost:
        print(_COST_NOTE)
        raise SystemExit(0)

    run(args.dump, args.eval_set)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the cost gate aborts without `--confirm-cost` ($0)**

Run: `python evals/ragas_eval.py --dump /nonexistent.jsonl`
Expected: prints the COST GATE note and exits 0 (no file read, no LLM call).

- [ ] **Step 3: Run the full test suite (still green, no LLM)**

Run: `python -m pytest evals/test_ragas_eval.py evals/test_answer_eval_capture.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add evals/ragas_eval.py
git commit -m "feat(evals): cost-gated RAGAS runner + Gemini/gte wiring (Phase 1 Task 6)"
```

---

## Task 7: Produce capture dump + run the matrix (MANUAL, cost-gated — STOP for OK)

**This task spends tokens. Per the cost rule, get explicit user OK before running either command.**

- [ ] **Step 1: State the cost estimate and get the user's OK**

Generation re-run (n=40) = the existing eval's generation provider (DeepInfra 70B or Groq, per your prior runs) + RAGAS scoring = a few hundred Gemini-2.5-flash calls (see `_COST_NOTE`). Present this to the user; do not proceed until they approve.

- [ ] **Step 2: Produce the capture-enabled dump (after OK)**

Run (matches the B1-on baseline arm — independent Gemini judge, n=40, seed 7, clean set):
```bash
python evals/answer_eval_full.py --provider deepinfra --judge-provider gemini \
  --eval-set evals/eval_set_v2_clean.jsonl --sample 40 --seed 7 \
  --dump evals/_capture_b1on.jsonl
```
Expected: `dumped 40 scored items -> evals/_capture_b1on.jsonl`, and the dump records now contain `answer` + `contexts`.

- [ ] **Step 3: Verify capture fields landed ($0)**

Run:
```bash
python -c "import json; r=[json.loads(l) for l in open('evals/_capture_b1on.jsonl',encoding='utf-8')]; assert r and 'answer' in r[0] and 'contexts' in r[0], 'capture fields missing'; print('capture OK', len(r), 'items, contexts len', len(r[0]['contexts']))"
```
Expected: `capture OK 40 items ...`.

- [ ] **Step 4: Run the RAGAS matrix (after OK)**

Run:
```bash
python evals/ragas_eval.py --dump evals/_capture_b1on.jsonl --confirm-cost
```
Expected: the `=== RAGAS DIAGNOSTIC MATRIX ===` table — overall + per-crop (rice/soybeans/poultry, rice recall marked `*`) + by-suppressed segmentation.

- [ ] **Step 5: Record results**

Update `PROGRESS.md` with the matrix output + interpretation (and note rice `context_recall` is provisional pending Phase 2). Gitignore the dump/log if large:
```bash
git add PROGRESS.md
git commit -m "docs(progress): Phase 1 RAGAS diagnostic matrix results"
```

---

## Self-Review (completed)

- **Spec coverage:** §2 metrics (faithfulness/answer_relevancy/context_precision/context_recall) → Task 6 `metrics` list. `answer_correctness` deferred → not in plan (correct). §4.1 capture extension → Task 1. §4.2 standalone scorer + Gemini/gte backend → Tasks 2-6. §5 per-crop + provisional + segment-by-suppressed → Tasks 4-5. §6 cost gate → Task 6 (`--confirm-cost`) + Task 7. §3 Issue 3 eval-only dep → Task 0. Testing (mocked, no live LLM) → Tasks 1-5 are pure/unit-tested; Task 6 runner has no unit test by design (live-LLM path). All covered.
- **Placeholder scan:** no TBD/TODO; every code step has complete code; commands have expected output.
- **Type consistency:** `_capture_fields` returns `{answer, contexts}` (Task 1) → consumed as `r["answer"]`/`r["contexts"]` (Tasks 2-3). `build_samples` returns `(samples, meta)` (Task 3) → used in `run()` (Task 6). `aggregate_scores(rows, metric_keys)` (Task 4) ← `format_report(report, metric_keys)` (Task 5) ← both called in `run()` with `metric_keys=[m.name for m in metrics]` (Task 6). `_PROVISIONAL_FOR_RICE`/`non_llm_context_recall_provisional` consistent between Task 4 impl and Task 5 rendering. Consistent.
