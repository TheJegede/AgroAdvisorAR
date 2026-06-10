# Guard Single-Call Merge (Latency Lever 2)

**Date:** 2026-06-10
**Status:** Design approved, pending spec review
**Lever:** Answer-latency lever 2 (real content latency, ~0.65s).

## Problem

The citation guard is the largest single stage of the critical path
(~1262ms avg, `backend/scripts/latency_probe.py`) and is **two serial LLM
round-trips**:

1. `decompose_claims` (`citation_guard_v2.py:74`) — one LLM call breaking the
   answer prose into ≤8 atomic claims.
2. `judge_claims_llm` (`citation_guard_v2.py:144`) — one LLM call labeling each
   claim ENTAILED/NEUTRAL/CONTRADICTED + score against evidence chunks.

`judge` depends on `decompose`'s output, so they are serial by data dependency —
neither can run before generation (both need the generated answer). ~0.65s each
on Groq 70b → ~1.3s total.

This guard is safety-critical: a past miscalibration blanked correct grounded
answers (see `PROGRESS.md` guard root-cause). Any change here is eval-gated.

## Goal & non-goals

**Goal:** halve the guard's LLM round-trips (~1.3s → ~0.65s) with **no change to
groundedness judgment quality and no answer ever skipping the guard.**

**Non-goals (YAGNI):**
- No conditional skip of the guard (rejected — reintroduces the exact
  ungrounded-overconfidence the guard exists to catch).
- No cheaper judge model (rejected — 8b is a weaker judge on safety-critical
  rates/products; keep 70b).
- No change to `score_answer`, suppression thresholds, escalation, or the
  `_SAFETY_CRITICAL_RE` rate-contradiction logic.

## Approach — merge decompose + judge into one LLM call

A single prompt extracts atomic claims from the answer AND labels each for
groundedness against the evidence, returning the same `list[ClaimResult]`
the two-step path produces. Same model (70b via `_providers()`), same
post-processing, one fewer hop.

### New function

`citation_guard_v2.judge_answer_llm(answer, chunks, run_config) -> list[ClaimResult]`

- Prompt = merge of `_DECOMPOSE_PROMPT` + `_JUDGE_PROMPT`: "From the ANSWER,
  extract up to 8 atomic factual claims. For each, label
  ENTAILED|NEUTRAL|CONTRADICTED vs the EVIDENCE with a 0.0–1.0 support score.
  Return ONLY a JSON array `[{"claim","label","score"}]`."
  Inputs: `answer[:2000]`, evidence = `chunks[:3]` each `[:CHUNK_PREVIEW_LENGTH]`.
- Reuses the EXISTING `judge_claims_llm` post-processing verbatim: markdown-fence
  strip, dict/wrapped-array normalization, label validation, 0–100 clamp,
  `_lexical_support` backstop (`score = max(llm_score, lexical)`), and the
  `CONTRADICTED + lexical >= LEXICAL_CONTRADICTION_GUARD → NEUTRAL` demotion.
- Returns `list[ClaimResult]` — identical shape, so `score_answer`, suppression,
  and `_is_safety_critical_contradiction` are untouched.

### `verify_answer` wiring (`citation_guard_v2.py:319`)

```python
chunk_texts = [c.get("snippet","") for c in chunks if c.get("snippet")]
results = None
if config.GUARD_MERGED_JUDGE:
    try:
        results = await judge_answer_llm(answer, chunk_texts, run_config)
    except Exception as e:
        logger.warning("Merged guard judge failed, falling back to two-step: %s", str(e)[:150])
        results = None
if not results:                                   # disabled, failed, or empty
    claims_text = await decompose_claims(answer, run_config)
    if not claims_text:
        return {"confidence_score": 1.0, "claim_verification": [], "escalation": None}
    if config.GROUNDEDNESS_JUDGE == "llm":
        results = await judge_claims_llm(claims_text, chunk_texts, run_config)
    else:
        results = await asyncio.to_thread(lambda: [verify_claim(c, chunk_texts) for c in claims_text])
confidence_score = score_answer(results)
return {"confidence_score": confidence_score, "claim_verification": results, "escalation": None}
```

`decompose_claims` and `judge_claims_llm` are **kept intact** — they are the
fallback path and remain used by tests/evals. Merged is a layer on top with the
full existing safety net (two-step → NLI) beneath it.

### Config

`config.GUARD_MERGED_JUDGE` (env `GUARD_MERGED_JUDGE`, default `true`). Allows
instant rollback to the two-step path without a deploy if the eval regresses.

## Eval gate (HARD REQUIREMENT before merge to main)

The guard's history mandates measured proof, not assumption.

1. Baseline (merged off): `cd evals && EVAL_WRITE_TO_DB=0 RUN_ANSWER_EVAL=1 \
   python eval_runner.py --eval-set eval_set_v2.jsonl` → record correctness,
   faithfulness, suppression.
2. After (merged on): same run.
3. Diagnostic: `python -m evals.diagnostic.runner --gold evals/diagnostic/gold_labels.jsonl`
   both ways.
4. **Pass criteria:** faithfulness and suppression must not regress beyond noise
   (~±1 item on n=20). If faithfulness drops, the merged prompt decomposes worse
   — keep `GUARD_MERGED_JUDGE=false` and stop.
5. Latency: `python -m scripts.latency_probe` confirms guard ~1.3s → ~0.65s.
6. Record both tables in this spec and `PROGRESS.md`.

## Testing (TDD)

- `judge_answer_llm`: mock LLM returning a JSON array → returns `ClaimResult`s
  with correct labels/scores; lexical backstop still lifts a grounded numeric
  claim the LLM under-scores; `CONTRADICTED` on high-lexical-overlap demoted to
  NEUTRAL; empty `chunks` → all NEUTRAL/0.0.
- `verify_answer`: with `GUARD_MERGED_JUDGE=true` calls `judge_answer_llm` once
  (assert two-step NOT called); on `judge_answer_llm` raising → falls back to
  `decompose_claims`+`judge_claims_llm`; malformed merged JSON → fallback; result
  shape feeds `score_answer` identically (suppression unchanged).
- Regression: an existing guard test fixture yields the same `confidence_score`
  band through the merged path as the two-step path.

## Files touched

- `backend/services/citation_guard_v2.py` — `judge_answer_llm` + `verify_answer` wiring
- `backend/config.py` — `GUARD_MERGED_JUDGE`
- `backend/tests/test_citation_guard*.py` — new + regression tests

## Verification

`scripts/latency_probe.py` guard column ~1262ms → ~650ms; SERIAL drops ~0.65s.
Eval tables show faithfulness/suppression flat. No answer bypasses the guard.
