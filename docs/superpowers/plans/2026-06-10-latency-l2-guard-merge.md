# Latency L2 — Guard Single-Call Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Build order: PLAN 2 of 4** (L4 → **L2** → L1 → L3). Independent of L1/L3; build after L4. Spec: `docs/superpowers/specs/2026-06-10-guard-merge-latency-design.md`.

**Goal:** Halve the citation guard's LLM round-trips (~1.3s → ~0.65s) by merging claim-decomposition and groundedness-judging into one LLM call, with no change to judgment quality and the existing two-step path retained as fallback.

**Architecture:** Today `verify_answer` (`backend/services/citation_guard_v2.py:319`) calls `decompose_claims` (LLM #1, answer → atomic claims) then `judge_claims_llm` (LLM #2, label each claim vs evidence) — serial. Add `judge_answer_llm(answer, chunks, run_config)`: ONE LLM call that extracts claims AND labels them, returning the same `list[ClaimResult]`. `verify_answer` uses it behind `config.GUARD_MERGED_JUDGE` (default on) and falls back to the two-step path on any failure. Same model (70b via `_providers()`), same post-processing.

**Tech Stack:** Python, langchain `HumanMessage`, the project's provider chain `utils.llm._providers`, pytest (`asyncio.run`).

---

## Background for an engineer with zero context

- **The guard is safety-critical.** A past miscalibration blanked correct grounded answers (see `PROGRESS.md` guard root-cause). This change MUST be eval-gated (Task 4) before merge to `main`; if faithfulness drops, ship with `GUARD_MERGED_JUDGE=false`.
- `backend/services/citation_guard_v2.py` key pieces:
  - `_providers()` (imported from `utils.llm`) yields the provider chain (Groq 70b → Gemini → …). Each provider is a langchain chat model; call `await llm.ainvoke([HumanMessage(content=prompt)], config=run_config)` → response with `.content` (a string).
  - `decompose_claims(answer, run_config)` → `list[str]` (≤8 claims). Prompt constant `_DECOMPOSE_PROMPT`.
  - `judge_claims_llm(claims, chunks, run_config)` → `list[ClaimResult]`. Prompt constant `_JUDGE_PROMPT`. Contains the post-processing we will reuse: markdown-fence strip, dict/wrapped-array normalization, label validation against `_NLI_LABELS`, 0–100 score clamp, `_lexical_support` backstop (`score = max(llm_score, lexical)`), and `CONTRADICTED + lexical >= LEXICAL_CONTRADICTION_GUARD → NEUTRAL`.
  - `verify_answer(answer, chunks, run_config)` → `{"confidence_score", "claim_verification", "escalation": None}`. Calls `decompose_claims` then `judge_claims_llm` (or NLI when `config.GROUNDEDNESS_JUDGE != "llm"`), then `score_answer(results)`.
  - `ClaimResult` is imported from `models.advisory` (`claim`, `label`, `score`).
  - `CHUNK_PREVIEW_LENGTH = 800`, `LEXICAL_CONTRADICTION_GUARD = 0.6`, `_NLI_LABELS = ["CONTRADICTED","ENTAILED","NEUTRAL"]`.
- Tests: `backend/tests/test_citation_guard_v2.py`. Run `cd backend && pytest tests/test_citation_guard_v2.py -v`. Async exercised via `asyncio.run`.

## File Structure

- Modify: `backend/config.py` — add `GUARD_MERGED_JUDGE`.
- Modify: `backend/services/citation_guard_v2.py` — add `_MERGED_JUDGE_PROMPT`, `_postprocess_judge_array` (extract shared post-processing), `judge_answer_llm`, and wire `verify_answer`.
- Modify: `backend/tests/test_citation_guard_v2.py` — new tests.

---

### Task 1: Config flag

**Files:**
- Modify: `backend/config.py` (after the `GROUNDEDNESS_JUDGE` line, ~line 79)

- [ ] **Step 1: Add the flag**

```python
# When true, the citation guard does claim-extraction AND groundedness-judging
# in ONE LLM call (judge_answer_llm) instead of two serial calls
# (decompose_claims -> judge_claims_llm). Falls back to the two-step path on any
# failure. Set false to roll back instantly without a deploy.
GUARD_MERGED_JUDGE = os.environ.get("GUARD_MERGED_JUDGE", "1") not in {"0", "false", "False"}
```

- [ ] **Step 2: Verify**

Run: `cd backend && python -c "import config; print(config.GUARD_MERGED_JUDGE)"`
Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "feat(guard): add GUARD_MERGED_JUDGE flag"
```

---

### Task 2: Extract shared judge post-processing (refactor, no behavior change)

The post-processing inside `judge_claims_llm` (parse → normalize → lexical backstop → ClaimResult list) must be reused by the merged path. Extract it into a helper so there is ONE implementation (DRY).

**Files:**
- Modify: `backend/services/citation_guard_v2.py`
- Test: `backend/tests/test_citation_guard_v2.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_citation_guard_v2.py`:

```python
from services import citation_guard_v2 as g


def test_postprocess_judge_array_applies_lexical_backstop():
    # LLM under-scores a grounded numeric claim; lexical overlap must lift it.
    claims = ["Apply 32 oz per acre of product X."]
    chunks = ["Use product X at 32 oz per acre during early season."]
    raw = '[{"claim": "Apply 32 oz per acre of product X.", "label": "NEUTRAL", "score": 0.1}]'
    results = g._postprocess_judge_array(raw, claims, chunks)
    assert len(results) == 1
    assert results[0].score >= 0.6  # lexical backstop lifted it


def test_postprocess_judge_array_demotes_false_contradiction():
    claims = ["Rice needs flooding at 4 inch depth."]
    chunks = ["Maintain a 4 inch flood depth on rice."]
    raw = '[{"claim": "Rice needs flooding at 4 inch depth.", "label": "CONTRADICTED", "score": 0.0}]'
    results = g._postprocess_judge_array(raw, claims, chunks)
    assert results[0].label == "NEUTRAL"  # high lexical overlap vetoes contradiction
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_citation_guard_v2.py -k postprocess_judge_array -v`
Expected: FAIL — `_postprocess_judge_array` does not exist.

- [ ] **Step 3: Implement the helper and call it from `judge_claims_llm`**

In `backend/services/citation_guard_v2.py`, add this function (place it just above `judge_claims_llm`):

```python
def _postprocess_judge_array(raw: str, claims: list[str], chunks: list[str]) -> list[ClaimResult] | None:
    """Parse a judge LLM's JSON array of {claim,label,score} into ClaimResults,
    applying the lexical backstop and false-contradiction demotion. Returns None
    if the response can't be coerced into one object per claim (caller falls back).
    """
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE).strip()
    parsed = json.loads(raw)
    # Normalize common deviations: a wrapped object, or a dict keyed by claim text.
    if isinstance(parsed, dict):
        for _key in ("claims", "results", "data"):
            if isinstance(parsed.get(_key), list):
                parsed = parsed[_key]
                break
        else:
            if parsed and all(isinstance(v, dict) for v in parsed.values()):
                parsed = [parsed.get(c, {}) for c in claims]
    if not isinstance(parsed, list):
        raise ValueError("judge response is not a list")
    out: list[ClaimResult] = []
    for claim, obj in zip(claims, parsed):
        if not isinstance(obj, dict):
            obj = {}
        label = obj.get("label", "NEUTRAL")
        if label not in _NLI_LABELS:
            label = "NEUTRAL"
        llm_score = float(obj.get("score", 0.0))
        if llm_score > 1.0:
            llm_score = llm_score / 100.0
        llm_score = min(1.0, max(0.0, llm_score))
        lexical = _lexical_support(claim, chunks[:3])
        score = max(llm_score, lexical)
        if label == "CONTRADICTED" and lexical >= LEXICAL_CONTRADICTION_GUARD:
            label = "NEUTRAL"
        out.append(ClaimResult(claim=claim, label=label, score=score))
    if len(out) != len(claims):
        return None
    return out
```

Then replace the parse+normalize+loop block **inside** `judge_claims_llm`'s `try:` (the code from `raw = re.sub(...)` through building `out` and `if len(out) == len(claims): return out`) with:

```python
            out = _postprocess_judge_array(resp.content, claims, chunks)
            if out is not None:
                return out
```

(Leave the surrounding `for llm in _providers():`, `evidence`/`claims_block` setup, `except` logging, and the NLI fallback line unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_citation_guard_v2.py -v`
Expected: the two new tests PASS and all pre-existing guard tests still PASS (behavior unchanged — pure extraction).

- [ ] **Step 5: Commit**

```bash
git add backend/services/citation_guard_v2.py backend/tests/test_citation_guard_v2.py
git commit -m "refactor(guard): extract _postprocess_judge_array (DRY judge parsing)"
```

---

### Task 3: judge_answer_llm — one-call merged judge (TDD)

**Files:**
- Modify: `backend/services/citation_guard_v2.py`
- Test: `backend/tests/test_citation_guard_v2.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_citation_guard_v2.py`:

```python
import asyncio


class _FakeLLM:
    def __init__(self, content):
        self._content = content

    async def ainvoke(self, messages, config=None):
        class _Resp:
            pass
        r = _Resp()
        r.content = self._content
        return r


def test_judge_answer_llm_extracts_and_labels_in_one_call(monkeypatch):
    content = (
        '[{"claim": "Soybeans in NE Arkansas are seeded at 140k seeds per acre.",'
        ' "label": "ENTAILED", "score": 0.9}]'
    )
    monkeypatch.setattr(g, "_providers", lambda: [_FakeLLM(content)])
    answer = "Soybeans in NE Arkansas are seeded at 140k seeds per acre."
    chunks = ["Recommended soybean seeding rate in northeast Arkansas is ~140,000 seeds/acre."]
    results = asyncio.run(g.judge_answer_llm(answer, chunks))
    assert len(results) == 1
    assert results[0].label == "ENTAILED"
    assert results[0].score >= 0.9


def test_judge_answer_llm_empty_chunks_returns_neutral(monkeypatch):
    monkeypatch.setattr(g, "_providers", lambda: [_FakeLLM("[]")])
    results = asyncio.run(g.judge_answer_llm("Some claim.", []))
    assert results == [] or all(r.label == "NEUTRAL" for r in results)


def test_judge_answer_llm_raises_when_all_providers_fail(monkeypatch):
    class _BadLLM:
        async def ainvoke(self, messages, config=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(g, "_providers", lambda: [_BadLLM()])
    import pytest
    with pytest.raises(Exception):
        asyncio.run(g.judge_answer_llm("Some claim.", ["evidence"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_citation_guard_v2.py -k judge_answer_llm -v`
Expected: FAIL — `judge_answer_llm` does not exist.

- [ ] **Step 3: Implement the merged prompt + function**

In `backend/services/citation_guard_v2.py`, add the prompt constant near `_JUDGE_PROMPT`:

```python
_MERGED_JUDGE_PROMPT = """You are auditing an agricultural advisory for groundedness.
From the ANSWER, extract up to 8 atomic factual claims (one fact each). Then label
each claim against the EVIDENCE passages:
- ENTAILED: the evidence supports the claim (paraphrase and equivalent numbers count).
- NEUTRAL: the evidence neither supports nor contradicts it.
- CONTRADICTED: the evidence states the opposite (e.g. a different rate/product, a negation).
Return ONLY a JSON array, one object per claim:
[{{"claim": "...", "label": "ENTAILED|NEUTRAL|CONTRADICTED", "score": 0.0-1.0}}]
score = your confidence the claim is supported (1.0 fully supported, 0.0 unsupported/contradicted).

EVIDENCE:
{evidence}

ANSWER:
{answer}
"""
```

Add the function (place it just below `judge_claims_llm`):

```python
async def judge_answer_llm(answer: str, chunks: list[str], run_config: dict | None = None) -> list[ClaimResult]:
    """One-call guard: extract atomic claims from `answer` AND label each for
    groundedness vs `chunks`, returning ClaimResults. Same model/post-processing
    as the two-step path, one fewer round-trip. Raises if every provider fails
    (caller in verify_answer falls back to decompose+judge)."""
    if not chunks:
        return []
    evidence = "\n---\n".join(chunk[:CHUNK_PREVIEW_LENGTH] for chunk in chunks[:3])
    prompt = _MERGED_JUDGE_PROMPT.format(evidence=evidence, answer=answer[:2000])
    last_err: Exception | None = None
    for llm in _providers():
        if llm is None:
            continue
        try:
            resp = await llm.ainvoke([HumanMessage(content=prompt)], config=run_config)
            # Re-derive the claim list from the response so post-processing aligns
            # one object per claim (the LLM both produced and labeled them).
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.content.strip(), flags=re.MULTILINE).strip()
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for _key in ("claims", "results", "data"):
                    if isinstance(parsed.get(_key), list):
                        parsed = parsed[_key]
                        break
            if not isinstance(parsed, list):
                raise ValueError("merged judge response is not a list")
            claims = [str(obj.get("claim", "")) for obj in parsed if isinstance(obj, dict)][:8]
            if not claims:
                return []
            out = _postprocess_judge_array(json.dumps(parsed[:8]), claims, chunks)
            if out is not None:
                return out
            raise ValueError("merged judge post-processing produced misaligned results")
        except Exception as e:
            last_err = e
            logger.warning("Merged guard judge provider failed, trying next: %s", str(e)[:150])
    raise last_err or RuntimeError("merged guard judge: no providers available")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_citation_guard_v2.py -k judge_answer_llm -v`
Expected: all three PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/citation_guard_v2.py backend/tests/test_citation_guard_v2.py
git commit -m "feat(guard): add judge_answer_llm single-call merged judge"
```

---

### Task 4: Wire verify_answer with fallback (TDD)

**Files:**
- Modify: `backend/services/citation_guard_v2.py` — `verify_answer` (line ~319)
- Test: `backend/tests/test_citation_guard_v2.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_citation_guard_v2.py`:

```python
def test_verify_answer_uses_merged_when_flag_on(monkeypatch):
    monkeypatch.setattr(config, "GUARD_MERGED_JUDGE", True)
    called = {"merged": 0, "decompose": 0}

    async def fake_merged(answer, chunks, run_config=None):
        called["merged"] += 1
        return [g.ClaimResult(claim="c", label="ENTAILED", score=0.9)]

    async def fake_decompose(answer, run_config=None):
        called["decompose"] += 1
        return ["c"]

    monkeypatch.setattr(g, "judge_answer_llm", fake_merged)
    monkeypatch.setattr(g, "decompose_claims", fake_decompose)
    out = asyncio.run(g.verify_answer("an answer", [{"snippet": "evidence"}]))
    assert called["merged"] == 1
    assert called["decompose"] == 0  # two-step NOT used
    assert "confidence_score" in out


def test_verify_answer_falls_back_when_merged_raises(monkeypatch):
    monkeypatch.setattr(config, "GUARD_MERGED_JUDGE", True)
    monkeypatch.setattr(config, "GROUNDEDNESS_JUDGE", "llm")
    used = {"decompose": 0, "judge": 0}

    async def boom(answer, chunks, run_config=None):
        raise RuntimeError("merged failed")

    async def fake_decompose(answer, run_config=None):
        used["decompose"] += 1
        return ["c"]

    async def fake_judge(claims, chunks, run_config=None):
        used["judge"] += 1
        return [g.ClaimResult(claim="c", label="ENTAILED", score=0.8)]

    monkeypatch.setattr(g, "judge_answer_llm", boom)
    monkeypatch.setattr(g, "decompose_claims", fake_decompose)
    monkeypatch.setattr(g, "judge_claims_llm", fake_judge)
    out = asyncio.run(g.verify_answer("an answer", [{"snippet": "evidence"}]))
    assert used["decompose"] == 1 and used["judge"] == 1  # fell back
    assert "confidence_score" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_citation_guard_v2.py -k verify_answer -v`
Expected: FAIL — `verify_answer` does not yet branch on `judge_answer_llm`.

- [ ] **Step 3: Rewrite `verify_answer`**

Replace the body of `verify_answer` (`citation_guard_v2.py:319`) with:

```python
async def verify_answer(answer: str, chunks: list[dict], run_config: dict | None = None) -> dict:
    """Orchestrate groundedness scoring. Prefers the one-call merged judge
    (GUARD_MERGED_JUDGE); falls back to decompose -> judge (or NLI) on any
    failure. Returns {confidence_score, claim_verification, escalation: None}."""
    chunk_texts = [c.get("snippet", "") for c in chunks if c.get("snippet")]

    results = None
    if config.GUARD_MERGED_JUDGE:
        try:
            results = await judge_answer_llm(answer, chunk_texts, run_config)
        except Exception as e:
            logger.warning("Merged guard failed, falling back to two-step: %s", str(e)[:150])
            results = None

    if not results:
        claims_text = await decompose_claims(answer, run_config)
        if not claims_text:
            return {"confidence_score": 1.0, "claim_verification": [], "escalation": None}
        if config.GROUNDEDNESS_JUDGE == "llm":
            results = await judge_claims_llm(claims_text, chunk_texts, run_config)
        else:
            results = await asyncio.to_thread(
                lambda: [verify_claim(c, chunk_texts) for c in claims_text]
            )

    confidence_score = score_answer(results)
    return {
        "confidence_score": confidence_score,
        "claim_verification": results,
        "escalation": None,
    }
```

Note: an empty `judge_answer_llm` result (`[]`, e.g. no chunks) is falsy and
routes to the two-step path, which itself returns `confidence_score: 1.0` for an
empty decomposition — preserving prior behavior.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_citation_guard_v2.py -v`
Expected: all PASS, including the pre-existing suite.

- [ ] **Step 5: Commit**

```bash
git add backend/services/citation_guard_v2.py backend/tests/test_citation_guard_v2.py
git commit -m "feat(guard): verify_answer uses merged judge with two-step fallback"
```

---

### Task 5: EVAL GATE (HARD REQUIREMENT before merge to main)

Do not merge to `main` until this passes. Needs repo-root `.env` with API keys.

- [ ] **Step 1: Baseline (merged OFF)**

Run:
```bash
cd evals && GUARD_MERGED_JUDGE=0 EVAL_WRITE_TO_DB=0 RUN_ANSWER_EVAL=1 \
  python eval_runner.py --eval-set eval_set_v2.jsonl
```
Record: correctness, faithfulness, suppression.

- [ ] **Step 2: After (merged ON)**

Run:
```bash
cd evals && GUARD_MERGED_JUDGE=1 EVAL_WRITE_TO_DB=0 RUN_ANSWER_EVAL=1 \
  python eval_runner.py --eval-set eval_set_v2.jsonl
```
Record the same three.

- [ ] **Step 3: Diagnostic both ways**

Run: `python -m evals.diagnostic.runner --gold evals/diagnostic/gold_labels.jsonl` with `GUARD_MERGED_JUDGE=0` then `=1`.

- [ ] **Step 4: Latency confirm**

Run: `cd backend && python -m scripts.latency_probe`
Expected: `guard` column ~1262ms → ~650ms; `SERIAL` down ~0.65s.

- [ ] **Step 5: Decision + record**

PASS criterion: faithfulness AND suppression do not regress beyond noise (~±1 item on n=20). If faithfulness drops, keep `GUARD_MERGED_JUDGE=false` and STOP (do not merge the default-on). Record both eval tables + the latency delta in `docs/superpowers/specs/2026-06-10-guard-merge-latency-design.md` (Eval gate section) and `PROGRESS.md`.

```bash
git add docs/superpowers/specs/2026-06-10-guard-merge-latency-design.md PROGRESS.md
git commit -m "docs(guard): record merged-judge eval + latency results"
```

---

## Self-Review (completed)

- **Spec coverage:** `judge_answer_llm` merged call (Task 3) ✓; reuse of existing post-processing via `_postprocess_judge_array` (Task 2) ✓; `verify_answer` flag + two-step/NLI fallback (Task 4) ✓; `GUARD_MERGED_JUDGE` config (Task 1) ✓; `score_answer`/suppression untouched (Task 4 returns same dict shape) ✓; eval gate hard requirement (Task 5) ✓.
- **Placeholders:** none — all code, prompts, and commands are concrete.
- **Type consistency:** `judge_answer_llm`, `_postprocess_judge_array`, `judge_claims_llm`, `decompose_claims`, `verify_answer` all return the documented types; `ClaimResult` used consistently; `_NLI_LABELS`/`LEXICAL_CONTRADICTION_GUARD`/`CHUNK_PREVIEW_LENGTH` referenced as defined in the module.
