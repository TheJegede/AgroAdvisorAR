# L1 Conditional-Rule Generation Lever Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generation preserve the condition→branch structure of conditional advisories (rate-by-soil, threshold-by-growth-stage, restriction-by-variety, timing-by-stage), and add a diagnostic gate sub-metric that measures it before/after.

**Architecture:** Two halves. (1) **Fix** — a prompt directive (`CONDITIONAL_RULE_BLOCK`) appended to the output instructions in `build_system_prompt`, telling the model never to emit a bare rate/threshold when the corpus ties it to a condition; it must state each condition with its matching value. No schema change — `Product.rate` is free text and conditional content also fits `recommended_actions`/`key_points`. (2) **Measure** — a new answer-side `conditional_judge` (Gemini 2.5-flash, mirrors `containment_judge`) that scores the *generated* answer against the gold conditional answer for whether the condition was preserved, surfaced as a new gate metric `conditional_completeness_rate`. The current gate buckets only on retrieval-containment and never reads the generated answer, so this metric is new instrumentation, not a tweak.

**Tech Stack:** Python 3, FastAPI backend, pytest, LangChain `ChatGoogleGenerativeAI` (Gemini 2.5-flash judge), the existing `evals/diagnostic/` harness.

**Why L1 first (from the D3 gate run, 2026-06-10):** B2 (gold fact verifiably retrieved, answer still wrong) dominated the judged items; `lever1_conditional_fraction_of_b2 = 0.357` (~5/14). The 7 conditional gold items all carry a dropped-condition failure mode — e.g. stink-bug threshold *5 per 10 sweeps weeks 1-2 / 10 weeks 3-4*, diquat *inactive in muddy water*, Beyond Xtra *Clearfield varieties only*, Linuron rate *by soil texture coarse/medium/fine*. Generation collapses these to a single bare number. This lever is generation-side, not retrieval/ingestion (those buckets B_MISS=4 / B3=1 were small and retrieval has 5 rejected levers already).

---

## File Structure

**Create:**
- `evals/diagnostic/conditional_judge.py` — `flatten_advisory()` (advisory dict → candidate text), `CompletenessResult`, `parse_conditional_response()`, `judge_conditional()` with transient-retry. One responsibility: answer-side conditional-completeness scoring.
- `evals/tests/test_diagnostic_conditional_judge.py` — unit tests for the above (LLM mocked).

**Modify:**
- `backend/utils/prompt.py` — add `CONDITIONAL_RULE_BLOCK`; append it inside `build_system_prompt` after the output-instructions block (applies to both diagnostic + informational intents).
- `backend/tests/test_prompt.py` — assert the directive is present in the built prompt.
- `evals/diagnostic/runner.py` — `ClassifiedItem` gains `cond_preserved: Optional[bool] = None`; `_classify_record` scores conditional items via `judge_conditional`; `build_report` emits `conditional_completeness_rate`.
- `evals/tests/test_diagnostic_runner.py` — assert the new metric; integration test for `_classify_record` wiring (judges + rag mocked).

**Not touched:** `backend/models/advisory.py` (no schema change — YAGNI), retrieval/ingestion (wrong lever per D3), `containment_judge.py` (the new judge is a separate file so the containment instrument stays clean).

---

## Task 1: Conditional-rule prompt directive

**Files:**
- Modify: `backend/utils/prompt.py` (add constant ~after line 33; wire into `build_system_prompt` ~line 107-116)
- Test: `backend/tests/test_prompt.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_prompt.py` (it already imports `build_system_prompt` and has the `_build` helper from line 41):

```python
# --- Task L1.1: conditional-rule directive --------------------------------

from utils.prompt import CONDITIONAL_RULE_BLOCK


def test_conditional_directive_present_in_diagnostic_prompt():
    prompt = _build()  # default diagnostic intent
    assert CONDITIONAL_RULE_BLOCK in prompt
    low = CONDITIONAL_RULE_BLOCK.lower()
    # The directive must name the failure mode it prevents.
    assert "condition" in low
    assert "soil" in low and "variety" in low and "stage" in low


def test_conditional_directive_present_in_informational_prompt():
    prompt = build_system_prompt(
        soil_context={"available": False}, weather_context={"available": False},
        retrieved_docs=[_doc("Rice Guide", "Thresholds", "treat at 6 per sq ft")],
        session_history=[], language="English", is_safety_critical=False,
        county_name="Arkansas", intent="informational",
    )
    assert CONDITIONAL_RULE_BLOCK in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prompt.py::test_conditional_directive_present_in_diagnostic_prompt -v`
Expected: FAIL — `ImportError: cannot import name 'CONDITIONAL_RULE_BLOCK'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/utils/prompt.py`, add the constant after `SAFETY_OVERRIDE` (after line 33):

```python
CONDITIONAL_RULE_BLOCK = """CONDITIONAL RULES — PRESERVE EVERY CONDITION:
Many recommendations in the retrieved context are conditional: a rate, threshold,
timing, or restriction that only holds under a stated condition. Examples of the
conditions you must keep: soil texture (coarse/medium/fine), crop growth stage or
weeks after heading, crop variety (e.g. Clearfield-only), water clarity, and
application timing (e.g. before bud break).
When the context states a conditional rule you MUST:
- State each condition together with its matching value or branch. Never collapse a
  multi-branch rule to a single number.
- If the rule has multiple branches (e.g. different rates per soil texture, or
  different thresholds per growth stage), list every branch with its condition.
- Never give a bare rate, threshold, or restriction without the condition that
  governs it when the context attaches one."""
```

Then in `build_system_prompt`, after the safety-override append block (after line 115, before `return`), add:

```python
    parts.append("")
    parts.append(CONDITIONAL_RULE_BLOCK)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_prompt.py -v`
Expected: PASS — both new tests plus all existing prompt tests green (no regression).

- [ ] **Step 5: Commit**

```bash
git add backend/utils/prompt.py backend/tests/test_prompt.py
git commit -m "feat(generation): conditional-rule directive (L1) preserves condition->branch"
```

---

## Task 2: `flatten_advisory` — advisory dict to candidate text

**Files:**
- Create: `evals/diagnostic/conditional_judge.py`
- Test: `evals/tests/test_diagnostic_conditional_judge.py`

- [ ] **Step 1: Write the failing test**

Create `evals/tests/test_diagnostic_conditional_judge.py`:

```python
# evals/tests/test_diagnostic_conditional_judge.py
from evals.diagnostic.conditional_judge import flatten_advisory


def test_flatten_includes_all_answer_bearing_fields():
    advisory = {
        "problem_summary": "Rice stink bug control.",
        "detailed_explanation": "Thresholds vary by week after heading.",
        "key_points": ["5 per 10 sweeps weeks 1-2", "10 per 10 sweeps weeks 3-4"],
        "recommended_actions": ["Sweep weekly after 75% heading"],
        "products_rates": [
            {"product": "Tenchu", "rate": "9 oz/A", "application_method": "foliar"}
        ],
        "warnings": ["Consult label"],
    }
    text = flatten_advisory(advisory)
    assert "5 per 10 sweeps weeks 1-2" in text
    assert "10 per 10 sweeps weeks 3-4" in text
    assert "Tenchu" in text and "9 oz/A" in text
    assert "Sweep weekly after 75% heading" in text


def test_flatten_skips_none_and_empty():
    advisory = {
        "problem_summary": "X",
        "detailed_explanation": None,
        "key_points": [],
        "recommended_actions": [],
        "products_rates": [],
        "warnings": [],
    }
    text = flatten_advisory(advisory)
    assert text.strip() == "X"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest evals/tests/test_diagnostic_conditional_judge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.diagnostic.conditional_judge'`.

- [ ] **Step 3: Write minimal implementation**

Create `evals/diagnostic/conditional_judge.py`:

```python
# evals/diagnostic/conditional_judge.py
"""Conditional-completeness judge: did the GENERATED answer preserve the
condition->branch structure of the gold conditional answer?

Separate from containment_judge: containment reads the retrieved CHUNKS, this
reads the generated ANSWER. Uses Gemini 2.5-flash — a different model from the
70B generator, so the generator never grades itself.
"""
import os
import re
import json
import time
from dataclasses import dataclass
from typing import Optional


def flatten_advisory(advisory: dict) -> str:
    """Join every answer-bearing field of an advisory into one candidate string."""
    parts: list[str] = []
    for key in ("problem_summary", "detailed_explanation"):
        val = advisory.get(key)
        if val:
            parts.append(str(val))
    for key in ("key_points", "recommended_actions", "warnings"):
        for item in advisory.get(key) or []:
            if item:
                parts.append(str(item))
    for pr in advisory.get("products_rates") or []:
        bits = [pr.get("product"), pr.get("rate"), pr.get("application_method")]
        line = " ".join(b for b in bits if b)
        if line:
            parts.append(line)
    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest evals/tests/test_diagnostic_conditional_judge.py -v`
Expected: PASS — both `flatten_advisory` tests green.

- [ ] **Step 5: Commit**

```bash
git add evals/diagnostic/conditional_judge.py evals/tests/test_diagnostic_conditional_judge.py
git commit -m "feat(diagnostic): flatten_advisory candidate-text helper for L1 judge"
```

---

## Task 3: `judge_conditional` — answer-side completeness judge

**Files:**
- Modify: `evals/diagnostic/conditional_judge.py`
- Test: `evals/tests/test_diagnostic_conditional_judge.py`

- [ ] **Step 1: Write the failing test**

Append to `evals/tests/test_diagnostic_conditional_judge.py`:

```python
import pytest

from evals.diagnostic.conditional_judge import (
    parse_conditional_response,
    build_conditional_prompt,
    judge_conditional,
    CompletenessResult,
    _is_transient,
)


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FlakyLLM:
    def __init__(self, error, fail_times, content='{"preserved": true, "missing": null}'):
        self.error = error
        self.fail_times = fail_times
        self.content = content
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.error
        return _FakeResp(self.content)


def test_parse_preserved_true():
    res = parse_conditional_response('{"preserved": true, "missing": null}')
    assert res.preserved is True
    assert res.missing is None


def test_parse_preserved_false_with_missing():
    res = parse_conditional_response(
        '{"preserved": false, "missing": "dropped the soil-texture branches"}'
    )
    assert res.preserved is False
    assert res.missing == "dropped the soil-texture branches"


def test_parse_strips_code_fence():
    res = parse_conditional_response('```json\n{"preserved": true, "missing": null}\n```')
    assert res.preserved is True


def test_parse_garbage_is_safe_not_preserved():
    # Unparseable judge output must never count as a pass.
    res = parse_conditional_response("the model rambled")
    assert res.preserved is False


def test_prompt_carries_gold_and_candidate():
    prompt = build_conditional_prompt(
        gold_answer="0.8 pt/A coarse, 1.6 pt/A medium, 2.4 pt/A fine soil",
        candidate_answer="Apply 1.6 pt/A.",
    )
    assert "0.8 pt/A coarse" in prompt
    assert "Apply 1.6 pt/A." in prompt
    assert "preserved" in prompt


def test_judge_retries_transient_then_succeeds():
    llm = _FlakyLLM(RuntimeError("503 UNAVAILABLE"), fail_times=2)
    res = judge_conditional("gold", "candidate", llm=llm, sleep=lambda _s: None)
    assert res.preserved is True
    assert llm.calls == 3


def test_judge_reraises_after_max_attempts():
    llm = _FlakyLLM(RuntimeError("503 UNAVAILABLE"), fail_times=99)
    with pytest.raises(RuntimeError):
        judge_conditional("g", "c", llm=llm, max_attempts=3, sleep=lambda _s: None)
    assert llm.calls == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest evals/tests/test_diagnostic_conditional_judge.py::test_parse_preserved_true -v`
Expected: FAIL — `ImportError: cannot import name 'parse_conditional_response'`.

- [ ] **Step 3: Write minimal implementation**

Append to `evals/diagnostic/conditional_judge.py`:

```python
_TRANSIENT_RE = re.compile(r"\b(503|429|unavailable|overloaded|deadline)\b", re.I)


def _is_transient(err: Exception) -> bool:
    return bool(_TRANSIENT_RE.search(str(err)))


JUDGE_MODEL = os.environ.get("CONDITIONAL_JUDGE_MODEL", "gemini-2.5-flash")


@dataclass
class CompletenessResult:
    preserved: bool
    missing: Optional[str]


JUDGE_SYSTEM = (
    "You are a conditional-completeness checker. You are given a GOLD ANSWER that "
    "contains a conditional rule — a rate, threshold, timing, or restriction that "
    "depends on a stated condition (e.g. soil texture, crop growth stage or weeks "
    "after heading, crop variety, water clarity, application timing) — and a "
    "CANDIDATE ANSWER produced by an advisory system. Decide ONLY whether the "
    "candidate preserves the SAME qualifying condition(s) and their matching "
    "value(s)/branch(es). Ignore wording, extra content, and citations. The "
    "candidate is preserved=true ONLY if every condition in the gold appears in the "
    "candidate with its corresponding branch. If the candidate gives a bare value "
    "without its governing condition, or drops a branch, preserved=false. Do NOT "
    "answer the farmer's question or add knowledge."
)

JUDGE_TEMPLATE = """GOLD ANSWER:
{gold_answer}

CANDIDATE ANSWER:
{candidate_answer}

Return ONLY a JSON object:
{{"preserved": <true if every gold condition appears in the candidate with its matching branch, else false>, "missing": "<short description of the dropped condition/branch, or null>"}}"""


def build_conditional_prompt(gold_answer: str, candidate_answer: str) -> str:
    return JUDGE_TEMPLATE.format(
        gold_answer=gold_answer, candidate_answer=candidate_answer
    )


def parse_conditional_response(raw: str) -> CompletenessResult:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    try:
        parsed = json.loads(raw)
        missing = parsed.get("missing")
        if missing is not None:
            missing = str(missing)
        return CompletenessResult(preserved=bool(parsed.get("preserved", False)),
                                  missing=missing)
    except Exception:
        # Unparseable → never count as a pass.
        return CompletenessResult(preserved=False, missing=None)


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


def judge_conditional(gold_answer: str, candidate_answer: str, llm=None,
                      max_attempts: int = 3, sleep=time.sleep) -> CompletenessResult:
    from langchain_core.messages import SystemMessage, HumanMessage
    messages = [
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=build_conditional_prompt(gold_answer, candidate_answer)),
    ]
    judge = llm if llm is not None else _get_judge()
    for attempt in range(1, max_attempts + 1):
        try:
            resp = judge.invoke(messages)
            return parse_conditional_response(resp.content)
        except Exception as err:  # noqa: BLE001 — re-raised below if not retryable
            if attempt >= max_attempts or not _is_transient(err):
                raise
            sleep(2 ** (attempt - 1))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest evals/tests/test_diagnostic_conditional_judge.py -v`
Expected: PASS — all parse/prompt/retry tests green.

- [ ] **Step 5: Commit**

```bash
git add evals/diagnostic/conditional_judge.py evals/tests/test_diagnostic_conditional_judge.py
git commit -m "feat(diagnostic): conditional-completeness judge (Gemini) for L1 measurement"
```

---

## Task 4: Gate metric `conditional_completeness_rate`

**Files:**
- Modify: `evals/diagnostic/runner.py` (`ClassifiedItem` ~line 31-37; `build_report` ~line 60-73)
- Test: `evals/tests/test_diagnostic_runner.py`

- [ ] **Step 1: Write the failing test**

Append to `evals/tests/test_diagnostic_runner.py` (update the `_item` helper to accept the new field, then add the metric test):

```python
def _item_cond(bucket, rule_type="conditional", cond_preserved=None):
    return ClassifiedItem(query="q", bucket=bucket, human_bucket=None,
                          abstained=False, rule_type=rule_type,
                          cond_preserved=cond_preserved)


def test_conditional_completeness_rate():
    items = [
        _item_cond(Bucket.B2, cond_preserved=True),
        _item_cond(Bucket.B2, cond_preserved=False),
        _item_cond(Bucket.B2, cond_preserved=True),
        _item_cond(Bucket.B2, rule_type="flat", cond_preserved=None),  # excluded
        _item_cond(Bucket.QUARANTINED, cond_preserved=None),           # excluded
    ]
    report = build_report(items)
    # 2 of 3 scored conditional items preserved the condition.
    assert report["conditional_completeness_rate"] == round(2 / 3, 3)
    assert report["conditional_scored_n"] == 3


def test_conditional_completeness_rate_none_when_unscored():
    items = [_item_cond(Bucket.B2, rule_type="flat", cond_preserved=None)]
    report = build_report(items)
    assert report["conditional_completeness_rate"] is None
    assert report["conditional_scored_n"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest evals/tests/test_diagnostic_runner.py::test_conditional_completeness_rate -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'cond_preserved'`.

- [ ] **Step 3: Write minimal implementation**

In `evals/diagnostic/runner.py`, add the field to `ClassifiedItem` (after line 37):

```python
@dataclass
class ClassifiedItem:
    query: str
    bucket: Bucket
    human_bucket: Optional[str]
    abstained: bool
    rule_type: Optional[str]
    cond_preserved: Optional[bool] = None
```

In `build_report`, before the `return` (after the `lever1_fraction` block, ~line 65), add:

```python
    scored = [it for it in items
              if it.rule_type == "conditional" and it.cond_preserved is not None]
    if scored:
        kept = sum(1 for it in scored if it.cond_preserved)
        cond_rate = round(kept / len(scored), 3)
    else:
        cond_rate = None
```

Then extend the returned dict:

```python
    return {
        "counts": counts,
        "total": len(items),
        "judge_error_rate": error_rate,
        "calibration_n": len(labeled),
        "lever1_conditional_fraction_of_b2": lever1_fraction,
        "conditional_completeness_rate": cond_rate,
        "conditional_scored_n": len(scored),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest evals/tests/test_diagnostic_runner.py -v`
Expected: PASS — new metric tests plus all existing runner tests green (the existing `_item` helper omits `cond_preserved`, which now defaults to `None`).

- [ ] **Step 5: Commit**

```bash
git add evals/diagnostic/runner.py evals/tests/test_diagnostic_runner.py
git commit -m "feat(diagnostic): conditional_completeness_rate gate metric"
```

---

## Task 5: Wire the judge into `_classify_record`

**Files:**
- Modify: `evals/diagnostic/runner.py` (`_classify_record` ~line 76-100)
- Test: `evals/tests/test_diagnostic_runner.py`

- [ ] **Step 1: Write the failing test**

Append to `evals/tests/test_diagnostic_runner.py`:

```python
import asyncio
import evals.diagnostic.runner as runner_mod
from evals.diagnostic.gold_schema import GoldRecord


def _gold(**kw):
    base = dict(
        query="how many stink bugs before I spray?", namespace="rice",
        source_in_index=True, gold_found=True,
        gold_answer="5 per 10 sweeps weeks 1-2, 10 per 10 sweeps weeks 3-4",
        gold_source="rice insect thresholds", gold_snippet="10 RSB per 10 sweeps",
        rule_type="conditional", human_bucket=None, set_aside=False,
    )
    base.update(kw)
    return GoldRecord(**base)


def test_classify_scores_conditional_item(monkeypatch):
    advisory = {"problem_summary": "Treat at 10 per 10 sweeps.",
                "key_points": [], "recommended_actions": [], "warnings": [],
                "products_rates": [], "detailed_explanation": None}

    async def fake_rag(**kwargs):
        return advisory, [{"snippet": "our threshold is 10 RSB per 10 sweeps"}]

    monkeypatch.setattr(runner_mod, "judge_containment",
                        lambda *a, **k: runner_mod.JudgeResult(span="10 RSB per 10 sweeps", partial=False))
    monkeypatch.setattr(runner_mod, "fact_retrieved", lambda *a, **k: True)
    monkeypatch.setattr(runner_mod, "judge_conditional",
                        lambda *a, **k: runner_mod.CompletenessResult(preserved=False, missing="weeks 1-2 branch"))

    item = asyncio.run(runner_mod._classify_record(_gold(), fake_rag))
    assert item.bucket is Bucket.B2
    assert item.cond_preserved is False


def test_classify_skips_conditional_scoring_for_flat_rule(monkeypatch):
    advisory = {"problem_summary": "x", "key_points": [], "recommended_actions": [],
                "warnings": [], "products_rates": [], "detailed_explanation": None}

    async def fake_rag(**kwargs):
        return advisory, [{"snippet": "y"}]

    monkeypatch.setattr(runner_mod, "judge_containment",
                        lambda *a, **k: runner_mod.JudgeResult(span="y", partial=False))
    monkeypatch.setattr(runner_mod, "fact_retrieved", lambda *a, **k: True)

    def _boom(*a, **k):
        raise AssertionError("judge_conditional must not run for flat rules")
    monkeypatch.setattr(runner_mod, "judge_conditional", _boom)

    item = asyncio.run(runner_mod._classify_record(_gold(rule_type="flat"), fake_rag))
    assert item.cond_preserved is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest evals/tests/test_diagnostic_runner.py::test_classify_scores_conditional_item -v`
Expected: FAIL — `AttributeError: module 'evals.diagnostic.runner' has no attribute 'judge_conditional'` (not imported yet) / `cond_preserved` not set.

- [ ] **Step 3: Write minimal implementation**

In `evals/diagnostic/runner.py`, add imports near the other diagnostic imports (after line 20):

```python
from evals.diagnostic.conditional_judge import (
    judge_conditional, flatten_advisory, CompletenessResult,
)
```

In `_classify_record`, after `bucket = classify(...)` (line 96) and before the `return`, add:

```python
    cond_preserved = None
    if (record.rule_type == "conditional" and record.gold_found
            and not record.set_aside):
        candidate = flatten_advisory(advisory_dict)
        cond_preserved = judge_conditional(record.gold_answer, candidate).preserved
```

Then update the return to pass it:

```python
    return ClassifiedItem(
        query=record.query, bucket=bucket, human_bucket=record.human_bucket,
        abstained=abstained, rule_type=record.rule_type,
        cond_preserved=cond_preserved,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest evals/tests/test_diagnostic_runner.py -v`
Expected: PASS — both wiring tests plus all existing runner tests green.

- [ ] **Step 5: Commit**

```bash
git add evals/diagnostic/runner.py evals/tests/test_diagnostic_runner.py
git commit -m "feat(diagnostic): score conditional items via answer-side judge in runner"
```

---

## Task 6: Baseline vs after measurement (manual) + record the result

**Files:**
- Modify: `PROGRESS.md` (append under the "▶ D3 GATE RUN" section)

This task produces no code — it runs the instrument before and after the Task 1 directive to confirm the lever moved the metric. The prompt change (Task 1) is already committed, so "baseline" means reverting it locally for one run.

- [ ] **Step 1: Capture the AFTER number (directive in place)**

Run (requires `GOOGLE_API_KEY` for the judge + a generator provider; per the D3 run use `LLM_PRIMARY=deepinfra` since Groq 70B is TPD-limited):

```bash
LLM_PRIMARY=deepinfra python -m evals.diagnostic.runner --gold evals/diagnostic/gold_labels.jsonl
```

Record `conditional_completeness_rate` and `conditional_scored_n` from the JSON output. Expect `conditional_scored_n == 7` (the 7 `rule_type=="conditional"` gold rows; note 2 of them are `set_aside` per the gold file — confirm the live `scored_n` and report whatever it is honestly).

- [ ] **Step 2: Capture the BASELINE number (directive removed)**

```bash
git stash push -- backend/utils/prompt.py
LLM_PRIMARY=deepinfra python -m evals.diagnostic.runner --gold evals/diagnostic/gold_labels.jsonl
git stash pop
```

Record `conditional_completeness_rate` from this run too.

- [ ] **Step 3: Record the before/after in PROGRESS.md**

Append a short block under the D3 section noting baseline → after `conditional_completeness_rate`, `conditional_scored_n`, the date, and the generator/judge used. State plainly whether the directive moved the metric; if it did not, that is a real result — L1 directive insufficient, escalate to L2 (few-shot conditional exemplars) or revisit. Do not claim a win the numbers don't show.

- [ ] **Step 4: Commit**

```bash
git add PROGRESS.md
git commit -m "docs(progress): L1 conditional-completeness before/after gate numbers"
```

---

## Self-Review

**Spec coverage:**
- Fix (prompt directive) → Task 1. ✓
- Measure (answer-side judge + metric) → Tasks 2 (flatten), 3 (judge), 4 (metric), 5 (wiring). ✓
- Before/after evidence → Task 6. ✓
- No schema change asserted → confirmed (Task list never touches `advisory.py`). ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/"write tests for the above" — every code step shows full code; every test step shows full test bodies. ✓

**Type consistency:**
- `CompletenessResult(preserved: bool, missing: Optional[str])` — defined Task 3, imported + constructed in Task 5 tests via `runner_mod.CompletenessResult`; runner imports it Task 5 Step 3. ✓
- `flatten_advisory(advisory: dict) -> str` — defined Task 2, used Task 5. ✓
- `judge_conditional(gold_answer, candidate_answer, llm=None, max_attempts=3, sleep=time.sleep)` — defined Task 3, called positionally `judge_conditional(record.gold_answer, candidate)` Task 5. ✓
- `ClassifiedItem.cond_preserved` default `None` — added Task 4, set Task 5, read in `build_report` Task 4. Existing `_item` helper (no `cond_preserved`) stays valid via the default. ✓
- `judge_containment` / `fact_retrieved` monkeypatched on `runner_mod` in Task 5 tests — both are module-level names in `runner.py` (imported there), so patchable. ✓

**Note on B2 semantics (carry into execution):** the gate buckets B2 on *retrieval* containment (`span_verified`), not on generated-answer correctness. `conditional_completeness_rate` is the FIRST signal in this harness that reads the generated answer. It is scored for ALL non-set-aside conditional gold items regardless of bucket (Task 5 condition is `rule_type/gold_found/not set_aside`, not `bucket is B2`), so it does not silently depend on the B2 proxy.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-10-l1-conditional-rule-generation-lever.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session via executing-plans, batch with checkpoints.

Which approach?
