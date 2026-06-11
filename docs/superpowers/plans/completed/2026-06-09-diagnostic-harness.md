# Diagnostic Harness (Pillar 0 Gate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the bucket-classifier harness that turns a human-labeled sample of failed eval items into a trustworthy bucket split (D3), so the rest of the pilot-readiness work is gated by evidence instead of guesses.

**Architecture:** A new `evals/diagnostic/` package. Pure, unit-testable decision logic (span verifier, bucket decision tree, pipeline-flag reader) is separated from I/O-bound pieces (the Gemini containment judge, the Pinecone `source_in_index` check, the live RAG run). The runner loads a human gold-labeled JSONL sample, runs the production RAG chain per item to capture `retrieved_chunks`, classifies each item through the decision tree, and emits a split report with a judge-error band computed against the human's own bucket labels.

**Tech Stack:** Python 3, pytest, `backend.services.rag.run_rag_query` (live pipeline), Gemini 2.5-flash via `langchain_google_genai` (containment judge — deliberately a *different* model from the DeepInfra/Groq 70B generator), Pinecone via the existing `backend.services` client.

**Key context from the codebase (verified):**
- `run_rag_query(message, county_fips, language, category, session_history)` returns `(advisory, retrieved_chunks)`. See `evals/answer_eval.py:45-59`.
- `retrieved_chunks` item shape: `{"document_title": str, "section_heading": str, "snippet": str}`. See `backend/services/rag.py:482-489`.
- `AdvisoryResponse` carries `suppressed: bool`, `escalation: str | None`, `confidence_score: float | None`. See `backend/models/advisory.py:60-66`.
- Existing answer-eval items (`evals/eval_set_v2.jsonl`) have shape `{query, chunk_id, chunk_text, document_title, namespace}`.
- Judge model for the gate is **Gemini 2.5-flash** (distinct from the 70B generator). `GOOGLE_API_KEY` already in `.env`.

**Scope boundary:** This plan builds the *harness* (the code). The human gold-labeling of ~30–40 items (Phase 1 of the implementation plan) is manual work that produces the input JSONL this harness consumes; it is **not** a coding task and is not in this plan. This plan ships when the harness can classify a labeled sample and print the D3 report.

---

## File structure

| File | Responsibility |
|---|---|
| `evals/diagnostic/__init__.py` | Package marker |
| `evals/diagnostic/gold_schema.py` | Validate + load the human gold-label JSONL records |
| `evals/diagnostic/span_verify.py` | Deterministic string-match: is a quoted span actually in the chunks? |
| `evals/diagnostic/pipeline_flags.py` | Read abstention state off an advisory dict |
| `evals/diagnostic/buckets.py` | Bucket enum + pure decision-tree `classify()` |
| `evals/diagnostic/containment_judge.py` | Gemini 2.5-flash span-or-null containment call |
| `evals/diagnostic/source_index.py` | Is a `document_title` ingested in Pinecone? |
| `evals/diagnostic/runner.py` | Tie it together: run RAG, classify sample, emit D3 report |
| `evals/diagnostic/gold_labels.example.jsonl` | One documented example gold record (the human's template) |
| `evals/tests/test_diagnostic_gold_schema.py` | Tests for schema validation |
| `evals/tests/test_diagnostic_span_verify.py` | Tests for span matcher |
| `evals/tests/test_diagnostic_pipeline_flags.py` | Tests for abstention reader |
| `evals/tests/test_diagnostic_buckets.py` | Tests for the decision tree |
| `evals/tests/test_diagnostic_containment_judge.py` | Tests for judge JSON parse (mocked LLM) |
| `evals/tests/test_diagnostic_source_index.py` | Tests for index check (mocked Pinecone) |
| `evals/tests/test_diagnostic_runner.py` | Tests for report assembly + error band (mocked deps) |

**Gold-label record schema** (the JSONL the human produces, validated by `gold_schema.py`):

```json
{
  "query": "How much paraquat per acre for burndown on my beans?",
  "namespace": "soybeans",
  "gold_found": true,
  "gold_answer": "Gramoxone SL 2.0 at 2.0–4.0 pt/acre for burndown",
  "gold_source": "MP44 Recommended Chemicals for Weed Control, Burndown section",
  "gold_snippet": "Gramoxone SL 2.0 ... 2.0 to 4.0 pt/A ... preplant burndown",
  "source_in_index": true,
  "rule_type": "flat",
  "human_bucket": "B2",
  "set_aside": false,
  "set_aside_reason": null
}
```

- `gold_found: false` → the fact is absent from the source of truth entirely (→ B-ABSENT). All gold_* fields may be null.
- `source_in_index` → is `gold_source`'s document ingested in Pinecone? Splits B-MISS from B3.
- `rule_type` ∈ `{"conditional", "flat"}` → the free Lever-1-substrate tag.
- `human_bucket` ∈ `{"B1","B2","B3","B4","B_MISS","B_ABSENT"}` → the human's own label, used to compute the judge-error band. May be `null` for items the human didn't hand-bucket.
- `set_aside: true` → quarantined hard case (no expert to adjudicate); counted but not classified.

---

## Task 1: Package scaffold + gold-label schema

**Files:**
- Create: `evals/diagnostic/__init__.py`
- Create: `evals/diagnostic/gold_schema.py`
- Create: `evals/diagnostic/gold_labels.example.jsonl`
- Test: `evals/tests/test_diagnostic_gold_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# evals/tests/test_diagnostic_gold_schema.py
import json
import pytest
from evals.diagnostic.gold_schema import GoldRecord, load_gold_records, GoldSchemaError


def _valid_dict():
    return {
        "query": "How much paraquat per acre?",
        "namespace": "soybeans",
        "gold_found": True,
        "gold_answer": "Gramoxone SL 2.0 at 2.0-4.0 pt/acre",
        "gold_source": "MP44 Burndown section",
        "gold_snippet": "Gramoxone SL 2.0 ... 2.0 to 4.0 pt/A",
        "source_in_index": True,
        "rule_type": "flat",
        "human_bucket": "B2",
        "set_aside": False,
        "set_aside_reason": None,
    }


def test_valid_record_parses():
    rec = GoldRecord.from_dict(_valid_dict())
    assert rec.query.startswith("How much")
    assert rec.gold_found is True
    assert rec.rule_type == "flat"


def test_gold_found_true_requires_snippet():
    d = _valid_dict()
    d["gold_snippet"] = None
    with pytest.raises(GoldSchemaError, match="gold_snippet"):
        GoldRecord.from_dict(d)


def test_gold_found_false_allows_null_gold_fields():
    d = _valid_dict()
    d["gold_found"] = False
    d["gold_answer"] = None
    d["gold_source"] = None
    d["gold_snippet"] = None
    d["source_in_index"] = None
    rec = GoldRecord.from_dict(d)
    assert rec.gold_found is False


def test_bad_rule_type_rejected():
    d = _valid_dict()
    d["rule_type"] = "branching"
    with pytest.raises(GoldSchemaError, match="rule_type"):
        GoldRecord.from_dict(d)


def test_load_gold_records_reads_jsonl(tmp_path):
    p = tmp_path / "gold.jsonl"
    p.write_text(json.dumps(_valid_dict()) + "\n", encoding="utf-8")
    recs = load_gold_records(p)
    assert len(recs) == 1
    assert recs[0].namespace == "soybeans"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_gold_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evals.diagnostic'`

- [ ] **Step 3: Write minimal implementation**

```python
# evals/diagnostic/__init__.py
```

```python
# evals/diagnostic/gold_schema.py
"""Schema + loader for the human-produced gold-label sample (D2 input)."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

VALID_RULE_TYPES = {"conditional", "flat"}
VALID_BUCKETS = {"B1", "B2", "B3", "B4", "B_MISS", "B_ABSENT"}


class GoldSchemaError(ValueError):
    """Raised when a gold-label record violates the schema."""


@dataclass
class GoldRecord:
    query: str
    namespace: str
    gold_found: bool
    gold_answer: Optional[str]
    gold_source: Optional[str]
    gold_snippet: Optional[str]
    source_in_index: Optional[bool]
    rule_type: Optional[str]
    human_bucket: Optional[str]
    set_aside: bool
    set_aside_reason: Optional[str]

    @classmethod
    def from_dict(cls, d: dict) -> "GoldRecord":
        if not d.get("query"):
            raise GoldSchemaError("query is required")
        gold_found = bool(d.get("gold_found"))
        if gold_found and not d.get("gold_snippet"):
            raise GoldSchemaError(
                "gold_found=True requires a gold_snippet (transcribe-don't-invent rule)"
            )
        rule_type = d.get("rule_type")
        if rule_type is not None and rule_type not in VALID_RULE_TYPES:
            raise GoldSchemaError(f"rule_type must be one of {VALID_RULE_TYPES}, got {rule_type!r}")
        human_bucket = d.get("human_bucket")
        if human_bucket is not None and human_bucket not in VALID_BUCKETS:
            raise GoldSchemaError(f"human_bucket must be one of {VALID_BUCKETS}, got {human_bucket!r}")
        return cls(
            query=d["query"],
            namespace=d.get("namespace", "general"),
            gold_found=gold_found,
            gold_answer=d.get("gold_answer"),
            gold_source=d.get("gold_source"),
            gold_snippet=d.get("gold_snippet"),
            source_in_index=d.get("source_in_index"),
            rule_type=rule_type,
            human_bucket=human_bucket,
            set_aside=bool(d.get("set_aside")),
            set_aside_reason=d.get("set_aside_reason"),
        )


def load_gold_records(path: Path) -> list[GoldRecord]:
    records = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(GoldRecord.from_dict(json.loads(line)))
    return records
```

```jsonl
{"query": "How much paraquat per acre for burndown on my beans?", "namespace": "soybeans", "gold_found": true, "gold_answer": "Gramoxone SL 2.0 at 2.0-4.0 pt/acre for burndown", "gold_source": "MP44 Recommended Chemicals for Weed Control, Burndown section", "gold_snippet": "Gramoxone SL 2.0 ... 2.0 to 4.0 pt/A ... preplant burndown", "source_in_index": true, "rule_type": "flat", "human_bucket": "B2", "set_aside": false, "set_aside_reason": null}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_gold_schema.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add evals/diagnostic/__init__.py evals/diagnostic/gold_schema.py evals/diagnostic/gold_labels.example.jsonl evals/tests/test_diagnostic_gold_schema.py
git commit -m "feat(diagnostic): gold-label schema + loader for D2 sample"
```

---

## Task 2: Deterministic span verifier

**Files:**
- Create: `evals/diagnostic/span_verify.py`
- Test: `evals/tests/test_diagnostic_span_verify.py`

**Why:** The containment judge returns a quoted span. We never trust it — we confirm the span verbatim exists in the chunks, tolerant only of whitespace/case so the model's quote-normalization doesn't cause false negatives. A span that doesn't match is treated as absent (auto-downgrade).

- [ ] **Step 1: Write the failing test**

```python
# evals/tests/test_diagnostic_span_verify.py
from evals.diagnostic.span_verify import span_in_chunks

CHUNKS = [
    {"snippet": "Apply Gramoxone SL 2.0 at 2.0 to 4.0 pt/A for preplant burndown."},
    {"snippet": "Inversions trap spray droplets near the ground."},
]


def test_exact_span_matches():
    assert span_in_chunks("2.0 to 4.0 pt/A", CHUNKS) is True


def test_whitespace_and_case_normalized():
    assert span_in_chunks("2.0   TO 4.0   PT/A", CHUNKS) is True


def test_absent_span_does_not_match():
    assert span_in_chunks("1.5 pt/A", CHUNKS) is False


def test_none_span_is_false():
    assert span_in_chunks(None, CHUNKS) is False


def test_empty_span_is_false():
    assert span_in_chunks("   ", CHUNKS) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_span_verify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evals.diagnostic.span_verify'`

- [ ] **Step 3: Write minimal implementation**

```python
# evals/diagnostic/span_verify.py
"""Deterministic verification that a judge-returned span is really in the chunks."""
import re
from typing import Optional


def _normalize(text: str) -> str:
    # Collapse all whitespace to single spaces, lowercase. No model involved.
    return re.sub(r"\s+", " ", text).strip().lower()


def span_in_chunks(span: Optional[str], chunks: list[dict]) -> bool:
    if not span or not span.strip():
        return False
    needle = _normalize(span)
    if not needle:
        return False
    for chunk in chunks:
        haystack = _normalize(chunk.get("snippet", ""))
        if needle in haystack:
            return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_span_verify.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add evals/diagnostic/span_verify.py evals/tests/test_diagnostic_span_verify.py
git commit -m "feat(diagnostic): deterministic span-in-chunks verifier"
```

---

## Task 3: Pipeline-flags (abstention) reader

**Files:**
- Create: `evals/diagnostic/pipeline_flags.py`
- Test: `evals/tests/test_diagnostic_pipeline_flags.py`

**Why:** Bucket 1 (correctly abstained) and the B-ABSENT→B1 mapping need to know whether the pipeline abstained. Abstention = the guard blanked the body (`suppressed`) OR attached an escalation.

- [ ] **Step 1: Write the failing test**

```python
# evals/tests/test_diagnostic_pipeline_flags.py
from evals.diagnostic.pipeline_flags import is_abstention


def test_suppressed_is_abstention():
    assert is_abstention({"suppressed": True, "escalation": None}) is True


def test_escalation_present_is_abstention():
    assert is_abstention({"suppressed": False, "escalation": "Call your county agent"}) is True


def test_plain_answer_is_not_abstention():
    assert is_abstention({"suppressed": False, "escalation": None}) is False


def test_missing_keys_default_not_abstention():
    assert is_abstention({}) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_pipeline_flags.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# evals/diagnostic/pipeline_flags.py
"""Read abstention state off an advisory dict (model_dump of AdvisoryResponse)."""


def is_abstention(advisory: dict) -> bool:
    if advisory.get("suppressed"):
        return True
    if advisory.get("escalation"):
        return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_pipeline_flags.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add evals/diagnostic/pipeline_flags.py evals/tests/test_diagnostic_pipeline_flags.py
git commit -m "feat(diagnostic): abstention reader for pipeline flags"
```

---

## Task 4: Bucket decision tree (pure)

**Files:**
- Create: `evals/diagnostic/buckets.py`
- Test: `evals/tests/test_diagnostic_buckets.py`

**Why:** The heart of the gate. A pure function over (gold record, judge result, pipeline abstention). No I/O — fully unit-testable. The judge result is passed in as a small structure so this stays deterministic.

Decision tree (in order):
1. `set_aside` → `QUARANTINED` (counted, not classified).
2. `gold_found is False` → `B_ABSENT`.
3. judge `partial` → `B4`.
4. judge span verified present in chunks → `B2`.
5. else (span null/unverifiable): `source_in_index` True → `B_MISS`; False → `B3`.

- [ ] **Step 1: Write the failing test**

```python
# evals/tests/test_diagnostic_buckets.py
from evals.diagnostic.buckets import Bucket, classify, JudgeResult
from evals.diagnostic.gold_schema import GoldRecord


def _gold(**over):
    base = {
        "query": "q", "namespace": "soybeans", "gold_found": True,
        "gold_answer": "a", "gold_source": "s", "gold_snippet": "snip",
        "source_in_index": True, "rule_type": "flat",
        "human_bucket": None, "set_aside": False, "set_aside_reason": None,
    }
    base.update(over)
    return GoldRecord.from_dict(base)


def test_set_aside_is_quarantined():
    rec = _gold(set_aside=True, set_aside_reason="conflicting pubs")
    assert classify(rec, JudgeResult(span="snip", partial=False), span_verified=True) is Bucket.QUARANTINED


def test_gold_not_found_is_absent():
    rec = _gold(gold_found=False, gold_answer=None, gold_source=None, gold_snippet=None, source_in_index=None)
    assert classify(rec, JudgeResult(span=None, partial=False), span_verified=False) is Bucket.B_ABSENT


def test_partial_is_b4():
    rec = _gold()
    assert classify(rec, JudgeResult(span="snip", partial=True), span_verified=True) is Bucket.B4


def test_verified_span_is_b2():
    rec = _gold()
    assert classify(rec, JudgeResult(span="snip", partial=False), span_verified=True) is Bucket.B2


def test_span_in_index_but_not_retrieved_is_b_miss():
    rec = _gold(source_in_index=True)
    assert classify(rec, JudgeResult(span=None, partial=False), span_verified=False) is Bucket.B_MISS


def test_span_absent_and_not_in_index_is_b3():
    rec = _gold(source_in_index=False)
    assert classify(rec, JudgeResult(span=None, partial=False), span_verified=False) is Bucket.B3


def test_judge_claims_span_but_string_match_fails_downgrades():
    # Judge returned a span, but the deterministic verifier rejected it → treat as absent.
    rec = _gold(source_in_index=False)
    assert classify(rec, JudgeResult(span="hallucinated", partial=False), span_verified=False) is Bucket.B3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_buckets.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# evals/diagnostic/buckets.py
"""Pure bucket decision tree (D2). No I/O — the judge result and the
deterministic span-verification outcome are passed in."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from evals.diagnostic.gold_schema import GoldRecord


class Bucket(str, Enum):
    B1 = "B1"            # correctly abstained (derived in the report layer)
    B2 = "B2"            # answerable, generation failed
    B3 = "B3"            # true corpus gap
    B4 = "B4"            # borderline / partial
    B_MISS = "B_MISS"    # retrieval miss (radioactive)
    B_ABSENT = "B_ABSENT"  # not in source of truth → feeds B1
    QUARANTINED = "QUARANTINED"  # set-aside hard case, no expert


@dataclass
class JudgeResult:
    span: Optional[str]
    partial: bool


def classify(record: GoldRecord, judge: JudgeResult, span_verified: bool) -> Bucket:
    if record.set_aside:
        return Bucket.QUARANTINED
    if not record.gold_found:
        return Bucket.B_ABSENT
    if judge.partial:
        return Bucket.B4
    if span_verified:
        return Bucket.B2
    # Span absent or failed deterministic verification → not in retrieved chunks.
    if record.source_in_index:
        return Bucket.B_MISS
    return Bucket.B3
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_buckets.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add evals/diagnostic/buckets.py evals/tests/test_diagnostic_buckets.py
git commit -m "feat(diagnostic): pure bucket decision tree"
```

---

## Task 5: Containment judge (Gemini 2.5-flash)

**Files:**
- Create: `evals/diagnostic/containment_judge.py`
- Test: `evals/tests/test_diagnostic_containment_judge.py`

**Why:** The single LLM node. Uses **Gemini 2.5-flash — deliberately a different model from the 70B generator** so the generator isn't grading its own failure. Strict output contract: JSON `{quoted_span: str|null, partial: bool}`. The judge only extracts a containing span; it never produces the answer. The test mocks the LLM so it runs offline and deterministically.

- [ ] **Step 1: Write the failing test**

```python
# evals/tests/test_diagnostic_containment_judge.py
from evals.diagnostic.containment_judge import parse_judge_response, build_judge_prompt


def test_parse_clean_json():
    res = parse_judge_response('{"quoted_span": "2.0 to 4.0 pt/A", "partial": false}')
    assert res.span == "2.0 to 4.0 pt/A"
    assert res.partial is False


def test_parse_null_span():
    res = parse_judge_response('{"quoted_span": null, "partial": false}')
    assert res.span is None


def test_parse_strips_code_fence():
    res = parse_judge_response('```json\n{"quoted_span": "x", "partial": true}\n```')
    assert res.span == "x"
    assert res.partial is True


def test_parse_garbage_is_safe_null():
    res = parse_judge_response("the model rambled with no json")
    assert res.span is None
    assert res.partial is False


def test_prompt_contains_gold_and_chunks_but_not_answer_request():
    prompt = build_judge_prompt(
        gold_answer="Gramoxone SL 2.0 at 2.0-4.0 pt/A",
        chunks=[{"snippet": "Apply Gramoxone SL 2.0 at 2.0 to 4.0 pt/A."}],
    )
    assert "2.0 to 4.0 pt/A" in prompt
    assert "Gramoxone SL 2.0 at 2.0-4.0" in prompt
    # The judge must never be asked to produce the answer.
    assert "quoted_span" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_containment_judge.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# evals/diagnostic/containment_judge.py
"""Containment judge: does the gold fact appear in the retrieved chunks?

Uses Gemini 2.5-flash — a DIFFERENT model from the DeepInfra/Groq 70B
generator, so the generator never grades its own failure. The judge returns
only a quoted span (or null) + a partial flag. It is never asked to author
the answer.
"""
import os
import json
from dataclasses import dataclass
from typing import Optional

from evals.diagnostic.buckets import JudgeResult

JUDGE_MODEL = os.environ.get("CONTAINMENT_JUDGE_MODEL", "gemini-2.5-flash")

JUDGE_SYSTEM = (
    "You are a containment checker. You are given a GOLD FACT and a set of "
    "RETRIEVED PASSAGES. Decide whether the gold fact is supported by the "
    "passages. You must NOT answer the farmer's question or add knowledge. "
    "Return ONLY the exact verbatim span from the passages that supports the "
    "gold fact, or null if no passage supports it."
)

JUDGE_TEMPLATE = """GOLD FACT:
{gold_answer}

RETRIEVED PASSAGES:
{chunks}

Return ONLY a JSON object:
{{"quoted_span": "<exact verbatim span from a passage that supports the gold fact, or null>", "partial": <true if a passage is related but only partially supports the fact, else false>}}"""


def build_judge_prompt(gold_answer: str, chunks: list[dict]) -> str:
    joined = "\n---\n".join(c.get("snippet", "") for c in chunks)
    return JUDGE_TEMPLATE.format(gold_answer=gold_answer, chunks=joined)


def parse_judge_response(raw: str) -> JudgeResult:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    try:
        parsed = json.loads(raw)
        span = parsed.get("quoted_span")
        if span is not None:
            span = str(span)
        return JudgeResult(span=span, partial=bool(parsed.get("partial", False)))
    except Exception:
        # Unparseable → safe absent. Never invent a span.
        return JudgeResult(span=None, partial=False)


_judge_llm = None


def _get_judge():
    global _judge_llm
    if _judge_llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _judge_llm = ChatGoogleGenerativeAI(
            model=JUDGE_MODEL,
            google_api_key=os.environ["GOOGLE_API_KEY"],
            temperature=0,
        )
    return _judge_llm


def judge_containment(gold_answer: str, chunks: list[dict]) -> JudgeResult:
    from langchain_core.messages import SystemMessage, HumanMessage
    messages = [
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=build_judge_prompt(gold_answer, chunks)),
    ]
    resp = _get_judge().invoke(messages)
    return parse_judge_response(resp.content)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_containment_judge.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add evals/diagnostic/containment_judge.py evals/tests/test_diagnostic_containment_judge.py
git commit -m "feat(diagnostic): Gemini containment judge with strict span contract"
```

---

## Task 6: `source_in_index` Pinecone check

**Files:**
- Create: `evals/diagnostic/source_index.py`
- Test: `evals/tests/test_diagnostic_source_index.py`

**Why:** Splits B-MISS (in index, not retrieved) from B3 (true gap). The human records `source_in_index` by hand during labeling, but this helper lets them confirm it mechanically: does any vector carry this `document_title`? The Pinecone client is injected so the test runs offline.

- [ ] **Step 1: Write the failing test**

```python
# evals/tests/test_diagnostic_source_index.py
from evals.diagnostic.source_index import doc_title_in_index


class _FakeIndex:
    def __init__(self, matches):
        self._matches = matches

    def query(self, *args, **kwargs):
        # Mimic pinecone query response shape.
        return {"matches": self._matches}


def test_title_present_returns_true():
    idx = _FakeIndex(matches=[{"id": "abc", "metadata": {"document_title": "MP44 Weed Control"}}])
    assert doc_title_in_index("MP44 Weed Control", index=idx, embed=lambda t: [0.0] * 8) is True


def test_title_absent_returns_false():
    idx = _FakeIndex(matches=[{"id": "abc", "metadata": {"document_title": "Rice Production Handbook"}}])
    assert doc_title_in_index("MP44 Weed Control", index=idx, embed=lambda t: [0.0] * 8) is False


def test_match_is_case_insensitive():
    idx = _FakeIndex(matches=[{"id": "abc", "metadata": {"document_title": "mp44 weed control"}}])
    assert doc_title_in_index("MP44 Weed Control", index=idx, embed=lambda t: [0.0] * 8) is True


def test_no_matches_returns_false():
    idx = _FakeIndex(matches=[])
    assert doc_title_in_index("anything", index=idx, embed=lambda t: [0.0] * 8) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_source_index.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# evals/diagnostic/source_index.py
"""Mechanical check: is a document_title present in the Pinecone index?

Pinecone has no full-scan-by-metadata, so we embed the title text and query
top-k across namespaces, then string-match the returned titles. Good enough to
confirm presence; the human still records the flag, this just assists.
"""
import os
from typing import Callable, Optional

NAMESPACES = ("rice", "soybeans", "poultry", "general")


def doc_title_in_index(
    document_title: str,
    index=None,
    embed: Optional[Callable[[str], list]] = None,
    top_k: int = 10,
) -> bool:
    if index is None or embed is None:
        index, embed = _default_index_and_embed()
    target = document_title.strip().lower()
    vec = embed(document_title)
    for ns in NAMESPACES:
        try:
            resp = index.query(vector=vec, top_k=top_k, include_metadata=True, namespace=ns)
        except TypeError:
            # Fake/simple indexes in tests accept no kwargs.
            resp = index.query()
        matches = resp.get("matches", []) if isinstance(resp, dict) else getattr(resp, "matches", [])
        for m in matches:
            md = m.get("metadata", {}) if isinstance(m, dict) else getattr(m, "metadata", {})
            if (md.get("document_title", "") or "").strip().lower() == target:
                return True
    return False


def _default_index_and_embed():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))
    from pinecone import Pinecone
    import config
    from services.embedding import MiniLMEmbeddings
    pc = Pinecone(api_key=config.PINECONE_API_KEY)
    index = pc.Index(config.PINECONE_INDEX_NAME)
    embedder = MiniLMEmbeddings(config.EMBEDDING_MODEL_PATH)
    return index, lambda t: embedder.embed_query(t)
```

> **Note for the implementer:** confirm `services.embedding.MiniLMEmbeddings` exposes `embed_query` and that `config` exposes `EMBEDDING_MODEL_PATH` before relying on `_default_index_and_embed()`. The unit tests inject fakes and do not exercise that path. If the real names differ, fix `_default_index_and_embed` only — the injected-dependency signature is what the tests pin.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_source_index.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add evals/diagnostic/source_index.py evals/tests/test_diagnostic_source_index.py
git commit -m "feat(diagnostic): Pinecone document_title presence check"
```

---

## Task 7: Runner — classify sample + D3 report with error band

**Files:**
- Create: `evals/diagnostic/runner.py`
- Test: `evals/tests/test_diagnostic_runner.py`

**Why:** Ties the pieces together and emits the gate output. Split the *report assembly* (pure, over already-classified items) from the *live RAG run* (I/O) so the report logic is unit-tested. The error band = disagreement rate between the harness bucket and the human's `human_bucket` on items the human labeled.

- [ ] **Step 1: Write the failing test**

```python
# evals/tests/test_diagnostic_runner.py
from evals.diagnostic.buckets import Bucket
from evals.diagnostic.runner import build_report, ClassifiedItem


def _item(bucket, human=None, abstained=False, rule_type="flat"):
    return ClassifiedItem(query="q", bucket=bucket, human_bucket=human,
                          abstained=abstained, rule_type=rule_type)


def test_split_counts_and_b1_derivation():
    items = [
        _item(Bucket.B2),
        _item(Bucket.B2),
        _item(Bucket.B3),
        _item(Bucket.B_ABSENT, abstained=True),   # → B1
        _item(Bucket.B_ABSENT, abstained=False),  # absent but pipeline answered: hallucination flag
        _item(Bucket.B_MISS),
        _item(Bucket.QUARANTINED),
    ]
    report = build_report(items)
    assert report["counts"]["B2"] == 2
    assert report["counts"]["B3"] == 1
    assert report["counts"]["B_MISS"] == 1
    assert report["counts"]["B1"] == 1            # one B_ABSENT + abstained
    assert report["counts"]["B_ABSENT_answered"] == 1  # hallucination flag
    assert report["counts"]["QUARANTINED"] == 1


def test_judge_error_band_from_human_agreement():
    items = [
        _item(Bucket.B2, human="B2"),
        _item(Bucket.B2, human="B2"),
        _item(Bucket.B3, human="B2"),   # disagreement
        _item(Bucket.B_MISS, human=None),  # not hand-labeled → excluded
    ]
    report = build_report(items)
    # 2/3 agree on hand-labeled items → error rate ~0.333
    assert report["judge_error_rate"] == round(1 / 3, 3)
    assert report["calibration_n"] == 3


def test_conditional_rule_fraction_for_lever1():
    items = [
        _item(Bucket.B2, rule_type="conditional"),
        _item(Bucket.B2, rule_type="flat"),
        _item(Bucket.B3, rule_type="flat"),
    ]
    report = build_report(items)
    # Of answerable (B2) items, 1 of 2 is conditional.
    assert report["lever1_conditional_fraction_of_b2"] == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_runner.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# evals/diagnostic/runner.py
"""D3 gate: classify a human gold-labeled sample and emit the split report.

The report layer (`build_report`) is pure over already-classified items, so it
is unit-tested. `run_diagnostic` does the live RAG + judge I/O and is run
manually against the real sample.
"""
import sys
import json
import asyncio
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from evals.diagnostic.gold_schema import load_gold_records, GoldRecord
from evals.diagnostic.buckets import Bucket, classify, JudgeResult
from evals.diagnostic.span_verify import span_in_chunks
from evals.diagnostic.pipeline_flags import is_abstention
from evals.diagnostic.containment_judge import judge_containment

_NAMESPACE_TO_CATEGORY = {
    "rice": "IN_SCOPE_RICE",
    "soybeans": "IN_SCOPE_SOYBEANS",
    "poultry": "IN_SCOPE_POULTRY",
    "general": "IN_SCOPE_GENERAL_AG",
}
EVAL_COUNTY_FIPS = "05031"  # Craighead County — SSURGO+NOAA injection succeeds


@dataclass
class ClassifiedItem:
    query: str
    bucket: Bucket
    human_bucket: Optional[str]
    abstained: bool
    rule_type: Optional[str]


def build_report(items: list[ClassifiedItem]) -> dict:
    counts = {b.value: 0 for b in Bucket}
    counts["B1"] = 0
    counts["B_ABSENT_answered"] = 0
    for it in items:
        if it.bucket is Bucket.B_ABSENT:
            if it.abstained:
                counts["B1"] += 1
            else:
                counts["B_ABSENT_answered"] += 1
        else:
            counts[it.bucket.value] += 1

    labeled = [it for it in items if it.human_bucket is not None]
    if labeled:
        agree = sum(1 for it in labeled if it.bucket.value == it.human_bucket)
        error_rate = round(1 - agree / len(labeled), 3)
    else:
        error_rate = None

    b2 = [it for it in items if it.bucket is Bucket.B2]
    if b2:
        cond = sum(1 for it in b2 if it.rule_type == "conditional")
        lever1_fraction = round(cond / len(b2), 3)
    else:
        lever1_fraction = None

    return {
        "counts": counts,
        "total": len(items),
        "judge_error_rate": error_rate,
        "calibration_n": len(labeled),
        "lever1_conditional_fraction_of_b2": lever1_fraction,
    }


async def _classify_record(record: GoldRecord, run_rag_query) -> ClassifiedItem:
    category = _NAMESPACE_TO_CATEGORY.get(record.namespace, "IN_SCOPE_GENERAL_AG")
    result = await run_rag_query(
        message=record.query,
        county_fips=EVAL_COUNTY_FIPS,
        language="en",
        category=category,
        session_history=[],
    )
    advisory, chunks = result if isinstance(result, tuple) else (result, [])
    advisory_dict = advisory.model_dump() if hasattr(advisory, "model_dump") else advisory
    abstained = is_abstention(advisory_dict)

    if record.set_aside or not record.gold_found:
        judge = JudgeResult(span=None, partial=False)
        verified = False
    else:
        judge = judge_containment(record.gold_answer, chunks)
        verified = span_in_chunks(judge.span, chunks)

    bucket = classify(record, judge, span_verified=verified)
    return ClassifiedItem(
        query=record.query, bucket=bucket, human_bucket=record.human_bucket,
        abstained=abstained, rule_type=record.rule_type,
    )


async def run_diagnostic(gold_path: Path) -> dict:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))
    from services.rag import run_rag_query
    records = load_gold_records(gold_path)
    items = [await _classify_record(r, run_rag_query) for r in records]
    return build_report(items)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, required=True,
                        help="Path to the human gold-labeled sample JSONL")
    args = parser.parse_args()
    report = asyncio.run(run_diagnostic(args.gold))
    print("\n=== D3 BUCKET SPLIT ===")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_runner.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full diagnostic suite**

Run: `cd c:\Users\jeged\Downloads\AgroAdvisor && python -m pytest evals/tests/test_diagnostic_*.py -v`
Expected: PASS (all diagnostic tests green)

- [ ] **Step 6: Commit**

```bash
git add evals/diagnostic/runner.py evals/tests/test_diagnostic_runner.py
git commit -m "feat(diagnostic): D3 runner + split report with judge-error band"
```

---

## Task 8: Document how to run the gate

**Files:**
- Modify: `PROGRESS.md` (append a "Pillar 0 diagnostic — how to run" note)
- Modify: `CLAUDE.md` (add the diagnostic command under Commands)

- [ ] **Step 1: Add the command to `CLAUDE.md` under `## Commands`**

Add this line in the Evals area:
```
**Diagnostic gate (D3):** `cd <repo> && python -m evals.diagnostic.runner --gold evals/diagnostic/gold_labels.jsonl`. Produces the bucket split (B1/B2/B3/B4/B-MISS/B-ABSENT) with judge-error band. Containment judge = Gemini 2.5-flash (`CONTAINMENT_JUDGE_MODEL`), distinct from the 70B generator.
```

- [ ] **Step 2: Append to `PROGRESS.md`**

Add under the answer-quality / RESUME HERE area a short note:
```
### Pillar 0 diagnostic harness — SHIPPED <date>
`evals/diagnostic/` classifies a human gold-labeled sample into buckets (D2/D3).
Re-scoped to solo: SAMPLE (~30-40), not census; search the index don't read it;
quarantine hard cases (no Extension expert). Run:
`python -m evals.diagnostic.runner --gold evals/diagnostic/gold_labels.jsonl`.
NEXT (human): produce gold_labels.jsonl (transcribe-don't-invent, 4 parts +
rule_type tag + human_bucket on the calibration slice), then read the split to
gate Phase 3 (Ingest / L1 / L2 / L3).
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md PROGRESS.md
git commit -m "docs(diagnostic): how to run the Pillar 0 gate"
```

---

## Self-review notes

- **Spec coverage:** D1 (expand eval) is a human/data step feeding `gold_labels.jsonl` — the harness consumes it; D2 (bucket classifier) = Tasks 1–6; D3 (split report + band) = Task 7. The three-scope model and 6-bucket tree are implemented in Task 4; B-MISS/B3 split via Task 6's `source_in_index`. The Lever-1 conditional-rule tag (free during labeling) is surfaced in the report (Task 7).
- **Type consistency:** `JudgeResult(span, partial)` defined in Task 4 (`buckets.py`), imported by Tasks 5 and 7. `Bucket` enum defined Task 4, used Tasks 4/7. `GoldRecord` defined Task 1, used Tasks 4/7. `ClassifiedItem` defined Task 7.
- **Gate honesty invariant:** the judge (Gemini) is never trusted — its span is re-verified by deterministic string match (Task 2) before B2 is assigned (Task 4). Unparseable judge output → safe-null, never an invented span (Task 5).
- **Out of scope (correctly):** human gold-labeling, eval-set expansion content, and the Phase 3 lever builds (gated on this harness's output).
