# Citation Guard Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the citation guard from deleting/flooring correct, grounded advisories by replacing the broken NLI judge with a reliable groundedness check and surgical (not nuclear) suppression.

**Architecture:** The guard pipeline stays (decompose answer → score each claim → suppress/escalate on low groundedness), but the *judge* changes. The tiny `nli-MiniLM2-L6-H768` CrossEncoder is retired from the hot path in favor of an LLM-as-judge that reuses the existing provider chain (Groq → Gemini → local Qwen). A cheap lexical backstop and a confidence-gated, **per-claim** contradiction rule replace the all-or-nothing override. Thresholds are recalibrated from per-namespace eval data instead of guessed.

**Tech Stack:** Python 3.13, FastAPI backend, LangChain provider clients (`ChatGroq`, `ChatGoogleGenerativeAI`, local Qwen adapter), pytest. Files: `backend/services/citation_guard_v2.py`, `backend/services/rag.py`, `backend/utils/prompt.py`, `backend/config.py`, `evals/answer_eval_full.py`.

---

## Why this plan exists (read first)

A live end-to-end trace (2026-05-31) localized "bad frontend responses" to the **citation guard**, NOT retrieval and NOT the generation model:

- **Retrieval is fine:** 6/6 sampled farmer queries returned on-topic chunks, gold in top-5.
- **Generation is fine:** Groq produced a correct, grounded sprayer-calibration answer.
- **The guard destroyed it:** NLI `confidence_score` 0.0 → body blanked → confidence "Low".
- **A/B proof:** same query with `NLI_CITATION_GUARD_ENABLED=0` returned a full, useful advisory.
- **The judge is confidently wrong:** on a rice query whose gold chunk literally contains `GPM = D x D x L`, the NLI labeled 7/8 true claims `CONTRADICTED` at prob 0.5–0.625 (e.g. "GPM is a unit of measurement for flow rate" → CONTRADICTED). No threshold fixes a model this wrong.

This supersedes the open items (P2.3) of `docs/superpowers/plans/2026-05-29-citation-guard-remediation.md`, which correctly predicted "wrong tool: per-claim hard NLI entailment" but stopped before replacing the model. The retrieval-v3 / rechunk paths are abandoned (deleted) — they were optimizing a layer that was never the bottleneck.

**Verification is free and repeatable** via the diagnostic scripts written during the investigation:
- `python evals/trace_retrieval.py` — retrieval-only, no LLM.
- `python evals/trace_generation.py` — one query end-to-end, dumps the advisory + guard outcome.
- `python evals/trace_pipeline_batch.py` — several queries, suppression/confidence summary.

All run against the local `.env`. Backend unit tests: `cd backend && python -m pytest tests/test_citation_guard_v2.py -q`.

---

## File structure

- `backend/services/citation_guard_v2.py` — the judge. Add LLM-judge scorer, lexical backstop, per-claim contradiction handling. Retire CrossEncoder from the hot path (keep behind a flag as offline fallback).
- `backend/services/rag.py` — `_postprocess_async` suppression logic: drop contradicted claims surgically; full-suppress only on safety-critical contradictions. Already holds `_strip_doc_prefix` (Phase 0).
- `backend/utils/prompt.py` — stop the LLM echoing "Document N:" into citations (cite by title).
- `backend/config.py` — new thresholds/flags, env-overridable.
- `evals/answer_eval_full.py` — per-namespace suppression/score reporter for calibration (Phase 4).
- `backend/tests/test_citation_guard_v2.py` — tests for every behavior change.

---

## Phase 0 — DONE this session (record only)

Shipped in this investigation; do not redo. Re-run `pytest tests/test_citation_guard_v2.py -q` to confirm (21 pass + 1 pre-existing stale failure `test_verifiable_text_includes_all_advisory_fields`).

- **Fix 1 — contradiction confidence gate** (`citation_guard_v2.py`): a `CONTRADICTED` argmax is only trusted when `contradiction_prob >= CONTRADICTION_MIN_PROB` (0.55); otherwise demote to entailed/neutral. Stops a single marginal false-contradiction from zeroing the whole answer.
- **Fix 2 — strip `Document N:`** (`rag.py` `_strip_doc_prefix`): applied in the title-match guard (so grounded citations match retrieved titles → confidence no longer auto-floored) and in `_advisory_to_verifiable_text` (so decomposition stops emitting "Document N is related to…" meta-claims).
- Tests added: `test_verify_claim_marginal_contradiction_demoted`, `test_verify_claim_confident_contradiction_kept`, `test_strip_doc_prefix`, `test_title_match_strips_document_prefix`, `test_verifiable_text_strips_document_prefix`.

**Measured effect:** the A/B query recovered (empty/Low/0.0 → full/High/0.43). Batch: 2/6 fully recovered. **Remaining 4/6 still suppressed because the NLI model is the binding constraint — that is what Phases 1–4 fix.**

---

## Phase 1 — Interim quick win: lexical-contradiction guard

**Rationale:** today's residual false suppressions (score exactly 0.0) come from the NLI confidently labeling *grounded paraphrases* CONTRADICTED. A claim that shares high content-token overlap with a chunk is restating it, not negating it — so a high-confidence "contradiction" with high lexical overlap is almost always a false positive. This is cheap (no new model/API) and ships before the LLM judge.

**Files:**
- Modify: `backend/services/citation_guard_v2.py` (`verify_claim`)
- Test: `backend/tests/test_citation_guard_v2.py`

- [ ] **Step 1: Write the failing test**

```python
def test_verify_claim_high_lexical_overlap_not_contradicted(monkeypatch):
    # A claim that restates the chunk (high content-token overlap) must not be
    # honored as CONTRADICTED even if the NLI is confident — that pattern is the
    # model's systematic false positive on grounded technical claims.
    mod = importlib.import_module("services.citation_guard_v2")
    fake_scores = np.array([[0.70, 0.15, 0.15]])  # confident CONTRADICTED argmax
    mock_model = MagicMock()
    mock_model.predict.return_value = fake_scores
    monkeypatch.setattr(mod, "_nli_model", mock_model)

    # claim restates the chunk almost verbatim → lexical overlap ~1.0
    result = mod.verify_claim(
        "The formula GPM = D x D x L estimates flow rate.",
        ["GPM = D x D x L. Formula: gallons per minute estimates flow rate."],
    )
    assert result.label != "CONTRADICTED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_citation_guard_v2.py::test_verify_claim_high_lexical_overlap_not_contradicted -v`
Expected: FAIL — label is `CONTRADICTED` (0.70 clears the 0.55 gate today).

- [ ] **Step 3: Add the constant**

In `citation_guard_v2.py`, beside `CONTRADICTION_MIN_PROB`:

```python
# A claim restating chunk content (high content-token overlap) cannot be a
# genuine contradiction. Above this lexical-support level, never honor a
# CONTRADICTED label — it is the NLI's systematic false positive on grounded
# paraphrase / technical claims.
LEXICAL_CONTRADICTION_GUARD = 0.6
```

- [ ] **Step 4: Implement the guard in `verify_claim`**

Compute `lexical` *before* the contradiction decision, then extend the demotion condition:

```python
    contradiction_prob = float(best_scores[0])
    entailment_prob = float(best_scores[1])
    neutral_prob = float(best_scores[2])
    lexical = _lexical_support(claim, chunks[:3])
    # Defect-A guard: don't trust an unconfident contradiction, AND never trust a
    # contradiction against a chunk the claim is clearly restating (high lexical
    # overlap). Demote to the better of entailment/neutral.
    if label == "CONTRADICTED" and (
        contradiction_prob < CONTRADICTION_MIN_PROB
        or lexical >= LEXICAL_CONTRADICTION_GUARD
    ):
        label = "ENTAILED" if entailment_prob >= neutral_prob else "NEUTRAL"

    score = max(entailment_prob, lexical)
```

(Remove the now-duplicate `lexical = _lexical_support(...)` line further down.)

- [ ] **Step 5: Run tests to verify pass**

Run: `cd backend && python -m pytest tests/test_citation_guard_v2.py -q`
Expected: new test passes; previously-passing tests still pass (1 pre-existing stale failure remains).

- [ ] **Step 6: Re-run the batch diagnostic**

Run: `python evals/trace_pipeline_batch.py`
Expected: fewer `score 0.00` suppressions than the 4/6 baseline. Record the new suppressed/escalated counts in PROGRESS.md.

- [ ] **Step 7: Commit**

```bash
git add backend/services/citation_guard_v2.py backend/tests/test_citation_guard_v2.py
git commit -m "fix(guard): don't honor NLI contradiction on high-lexical-overlap claims"
```

---

## Phase 2 — The real fix: LLM-as-judge groundedness

**Rationale:** the MiniLM NLI is OOD on agricultural PDFs + technical/formula claims. Replace it with an LLM grounding judge that reuses the existing provider chain. The guard already makes one LLM call (claim decomposition); fold judging into a single call so marginal cost is ~one call per query. Keep the lexical backstop. Keep the CrossEncoder only as an offline fallback behind a flag.

**Files:**
- Modify: `backend/services/citation_guard_v2.py` (add `judge_claims_llm`, rewire `verify_answer`)
- Modify: `backend/config.py` (flag)
- Test: `backend/tests/test_citation_guard_v2.py`

- [ ] **Step 1: Add the config flag**

In `config.py`:

```python
# Groundedness judge: "llm" (default) reuses the provider chain; "nli" keeps the
# legacy CrossEncoder for offline/no-API runs.
GROUNDEDNESS_JUDGE = os.environ.get("GROUNDEDNESS_JUDGE", "llm")
```

- [ ] **Step 2: Write the failing test for the LLM judge parser**

```python
def test_judge_claims_llm_parses_labels_and_scores(monkeypatch):
    mod = importlib.import_module("services.citation_guard_v2")

    class FakeResp:
        content = (
            '[{"claim":"GPM = D x D x L estimates flow.","label":"ENTAILED","score":0.9},'
            '{"claim":"Apply 999 lb N/ac.","label":"CONTRADICTED","score":0.0}]'
        )

    class FakeLLM:
        async def ainvoke(self, messages):
            return FakeResp()

    monkeypatch.setattr(mod, "_judge_providers", lambda: [FakeLLM()])
    import asyncio
    results = asyncio.run(mod.judge_claims_llm(
        ["GPM = D x D x L estimates flow.", "Apply 999 lb N/ac."],
        ["GPM = D x D x L. Apply 150 lb N/ac at green-up."],
    ))
    assert results[0].label == "ENTAILED" and results[0].score >= 0.8
    assert results[1].label == "CONTRADICTED"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_citation_guard_v2.py::test_judge_claims_llm_parses_labels_and_scores -v`
Expected: FAIL — `judge_claims_llm` / `_judge_providers` not defined.

- [ ] **Step 4: Implement the judge**

In `citation_guard_v2.py`:

```python
_JUDGE_PROMPT = """You are auditing an agricultural advisory for groundedness.
Given the EVIDENCE passages and a list of CLAIMS, label each claim:
- ENTAILED: the evidence supports the claim (paraphrase and equivalent numbers count).
- NEUTRAL: the evidence neither supports nor contradicts it.
- CONTRADICTED: the evidence states the opposite (e.g. a different rate/product, a negation).
Return ONLY a JSON array, one object per claim, same order:
[{{"claim": "...", "label": "ENTAILED|NEUTRAL|CONTRADICTED", "score": 0.0-1.0}}]
score = your confidence the claim is supported (1.0 fully supported, 0.0 unsupported/contradicted).

EVIDENCE:
{evidence}

CLAIMS:
{claims}
"""


def _judge_providers():
    # Same ordering as decomposition: reuse the configured provider chain.
    return _decompose_providers()


async def judge_claims_llm(claims: list[str], chunks: list[str]) -> list[ClaimResult]:
    """Score claims for groundedness with an LLM judge (provider chain), with a
    lexical backstop so specific grounded numbers/products are never under-scored."""
    if not claims:
        return []
    if not chunks:
        return [ClaimResult(claim=c, label="NEUTRAL", score=0.0) for c in claims]
    evidence = "\n---\n".join(ch[:800] for ch in chunks[:3])
    claims_block = "\n".join(f"{i+1}. {c}" for i, c in enumerate(claims))
    prompt = _JUDGE_PROMPT.format(evidence=evidence, claims=claims_block)
    for llm in _judge_providers():
        if llm is None:
            continue
        try:
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp.content.strip(), flags=re.MULTILINE).strip()
            parsed = json.loads(raw)
            out: list[ClaimResult] = []
            for claim, obj in zip(claims, parsed):
                label = obj.get("label", "NEUTRAL")
                if label not in _NLI_LABELS:
                    label = "NEUTRAL"
                llm_score = float(obj.get("score", 0.0))
                lexical = _lexical_support(claim, chunks[:3])
                score = max(llm_score, lexical)
                # Lexical backstop also vetoes false contradictions on restated content.
                if label == "CONTRADICTED" and lexical >= LEXICAL_CONTRADICTION_GUARD:
                    label = "NEUTRAL"
                out.append(ClaimResult(claim=claim, label=label, score=score))
            if len(out) == len(claims):
                return out
        except Exception as e:
            logger.warning("LLM groundedness judge failed, trying next: %s", str(e)[:150])
    # Fallback: legacy NLI per-claim.
    return [verify_claim(c, chunks) for c in claims]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_citation_guard_v2.py::test_judge_claims_llm_parses_labels_and_scores -v`
Expected: PASS.

- [ ] **Step 6: Write the failing test for `verify_answer` routing**

```python
def test_verify_answer_uses_llm_judge_when_configured(monkeypatch):
    mod = importlib.import_module("services.citation_guard_v2")
    import asyncio

    async def fake_decompose(answer):
        return ["claim one"]

    async def fake_judge(claims, chunks):
        from models.advisory import ClaimResult
        return [ClaimResult(claim="claim one", label="ENTAILED", score=0.88)]

    monkeypatch.setattr(mod, "decompose_claims", fake_decompose)
    monkeypatch.setattr(mod, "judge_claims_llm", fake_judge)
    monkeypatch.setattr(mod.config, "GROUNDEDNESS_JUDGE", "llm")

    out = asyncio.run(mod.verify_answer("some answer", [{"snippet": "evidence"}]))
    assert out["confidence_score"] == 0.88
    assert out["claim_verification"][0].label == "ENTAILED"
```

- [ ] **Step 7: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_citation_guard_v2.py::test_verify_answer_uses_llm_judge_when_configured -v`
Expected: FAIL — `verify_answer` still calls the NLI path.

- [ ] **Step 8: Rewire `verify_answer`**

Replace the scoring block in `verify_answer`:

```python
    claims_text = await decompose_claims(answer)
    if not claims_text:
        return {"confidence_score": 1.0, "claim_verification": [], "escalation": None}

    if config.GROUNDEDNESS_JUDGE == "llm":
        results = await judge_claims_llm(claims_text, chunk_texts)
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

- [ ] **Step 9: Run full guard suite**

Run: `cd backend && python -m pytest tests/test_citation_guard_v2.py -q`
Expected: all pass except the pre-existing stale failure.

- [ ] **Step 10: End-to-end check with the real judge**

Run: `python evals/trace_pipeline_batch.py` (uses local `.env`; `GROUNDEDNESS_JUDGE=llm` default).
Expected: the rice irrigation / GPM query and other grounded answers are no longer suppressed; record before/after suppression counts in PROGRESS.md.

- [ ] **Step 11: Commit**

```bash
git add backend/services/citation_guard_v2.py backend/config.py backend/tests/test_citation_guard_v2.py
git commit -m "feat(guard): LLM-as-judge groundedness, retire MiniLM NLI from hot path"
```

---

## Phase 3 — Surgical suppression (stop nuking the whole answer)

**Rationale:** even with a good judge, "any one CONTRADICTED → delete entire advisory" is brittle. Drop the offending claim and re-score the rest; reserve full suppression for contradictions that touch safety-critical content (a product or rate).

**Files:**
- Modify: `backend/services/citation_guard_v2.py` (`score_answer` → return structured outcome) and/or `rag.py` suppression block
- Test: `backend/tests/test_citation_guard_v2.py`

- [ ] **Step 1: Write the failing test**

```python
def test_score_answer_drops_single_contradiction_keeps_rest():
    # One contradicted claim among grounded ones should NOT zero the whole answer;
    # the contradicted claim is dropped and the rest scored.
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [
        ClaimResult(claim="A grounded.", label="ENTAILED", score=0.9),
        ClaimResult(claim="B grounded.", label="ENTAILED", score=0.8),
        ClaimResult(claim="C off-topic.", label="CONTRADICTED", score=0.0),
    ]
    score = mod.score_answer(claims)
    assert score > 0.2  # not suppressed; ~mean(0.9, 0.8)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_citation_guard_v2.py::test_score_answer_drops_single_contradiction_keeps_rest -v`
Expected: FAIL — current `score_answer` returns 0.0 on any contradiction.

- [ ] **Step 3: Update `score_answer`**

```python
def score_answer(results: list[ClaimResult]) -> float:
    """Groundedness = mean support of NON-contradicted claims. A contradicted
    claim is dropped (it will be surgically removed from the advisory upstream),
    not used to zero an otherwise grounded answer. Empty list → 1.0. All claims
    contradicted → 0.0."""
    if not results:
        return 1.0
    kept = [r for r in results if r.label != "CONTRADICTED"]
    if not kept:
        return 0.0
    return float(sum(r.score for r in kept) / len(kept))
```

- [ ] **Step 4: Update the existing contradiction test to the new contract**

`test_score_answer_contradiction_forces_suppression` asserted any contradiction → 0.0. Replace it with a test where **all** claims are contradicted → 0.0, and keep the mixed case in the Step 1 test.

```python
def test_score_answer_all_contradicted_suppresses():
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [ClaimResult(claim="x", label="CONTRADICTED", score=0.0),
              ClaimResult(claim="y", label="CONTRADICTED", score=0.0)]
    assert mod.score_answer(claims) == 0.0
```

- [ ] **Step 5: Run guard suite**

Run: `cd backend && python -m pytest tests/test_citation_guard_v2.py -q`
Expected: pass (minus the pre-existing stale failure).

- [ ] **Step 6: (Optional safety) flag safety-critical contradictions**

If `claim_verification` contains a CONTRADICTED claim whose text mentions a rate/unit (regex `\d`, `lb`, `oz`, `qt`, `/ac`, `gpa`) or a product name, keep the full-suppression path in `rag.py`. Add a unit test for the rate case. Document the decision in the plan if you skip it.

- [ ] **Step 7: Commit**

```bash
git add backend/services/citation_guard_v2.py backend/tests/test_citation_guard_v2.py
git commit -m "fix(guard): drop contradicted claim instead of suppressing whole answer"
```

---

## Phase 4 — Recalibrate thresholds from per-namespace data

**Rationale:** `SUPPRESSION_THRESHOLD=0.2` / `ESCALATION_THRESHOLD=0.4` are guesses made against the broken NLI. With the LLM judge, the score distribution changes — recalibrate from data, per crop.

**Files:**
- Modify: `evals/answer_eval_full.py` (per-namespace reporter — may already segment; extend if not)
- Modify: `backend/config.py` (make thresholds env-overridable if not already)
- Doc: record chosen thresholds + the distribution they came from in PROGRESS.md

- [ ] **Step 1:** Make thresholds env-overridable in `config.py` and have `citation_guard_v2.py` read them from config (not module constants), e.g. `SUPPRESSION_THRESHOLD = float(os.environ.get("GUARD_SUPPRESSION_THRESHOLD", "0.2"))`.
- [ ] **Step 2:** Run the per-namespace eval with the LLM judge: `python evals/answer_eval_full.py --provider local` (free, no quota) and capture suppression rate + mean `confidence_score` for rice / soybeans / poultry.
- [ ] **Step 3:** Pick thresholds that hit a defensible suppression band (e.g. suppress only the bottom decile of grounded answers) at a measured correctness floor. Record the numbers.
- [ ] **Step 4:** Re-run `evals/trace_pipeline_batch.py` to confirm the new operating point. Commit config + PROGRESS update.

---

## Phase 5 — Stop "Document N:" at the source (prose + prompt)

**Rationale:** Phase 0 strips the prefix for matching/verification, but the **user-facing** prose still reads "According to Document 4: …". Fix the prompt so the model cites by title, and strip any residual prefix from displayed prose.

**Files:**
- Modify: `backend/utils/prompt.py:74` and the OUTPUT_INSTRUCTIONS citation guidance
- Modify: `backend/services/rag.py` (apply `_strip_doc_prefix` to displayed citation titles + cause/action prose, not just the verifiable text)
- Test: `backend/tests/test_prompt.py` (or extend guard tests)

- [ ] **Step 1: Write the failing test** that `build_system_prompt` labels retrieved docs by title without forcing a "Document N:" citation convention the model echoes (assert the citation instruction tells the model to cite the document **title**, not "Document N").
- [ ] **Step 2:** Run to confirm fail.
- [ ] **Step 3:** Change `prompt.py:74` to label context as `"[{title} — {section}] {content}"` (or keep an internal index but instruct the model in OUTPUT_INSTRUCTIONS to cite by `document_title`). Update the citation instruction text.
- [ ] **Step 4:** In `rag.py`, normalize displayed citation titles and strip residual `Document N:` from `likely_causes[].explanation` / `recommended_actions` before returning.
- [ ] **Step 5:** Run `evals/trace_generation.py`; confirm citations + prose are clean. Commit.

---

## Phase 6 — Config audit (prod ≠ what we think)

**Rationale:** the local `.env` resolved to `PINECONE_INDEX_NAME=agroar-prod` (legacy MiniLM) + `EMBEDDING_MODEL_PATH=…/models/agroar-embeddings-v2` (the train-on-test contaminated fine-tune), NOT the validated `agroar-prod-gte` + `thenlper/gte-base`. If HF prod is also misconfigured, prod is serving the worst retrieval config.

**This is a verification task, not TDD.**

- [ ] **Step 1:** Confirm the local `.env` resolved index + embedder (already observed: legacy + fine-tune). Decide the intended local config and document it.
- [ ] **Step 2:** Check the HF Space secrets/variables: confirm `PINECONE_INDEX_NAME` and `EMBEDDING_MODEL_PATH` on the deployed backend. If they point at gte → prod is fine, local is just stale. If legacy → prod is mis-served; fix the HF env to `agroar-prod-gte` + `thenlper/gte-base`.
- [ ] **Step 3:** Record the finding in PROGRESS.md. If local should match prod, update local `.env` to gte and re-run `trace_retrieval.py` to confirm retrieval parity.

> Note: the guard fixes (Phases 0–3) are **config-independent** — they help on legacy and gte alike. Phase 6 is a separate correctness issue surfaced by the same investigation.

---

## Self-review checklist (run before execution)

- [ ] Every phase maps to a recommendation from the 2026-05-31 diagnosis (lexical guard, LLM judge, surgical suppression, recalibration, prose/prompt cleanup, config audit). ✔
- [ ] No placeholders: each code step shows real code; each run step shows the command + expected result.
- [ ] Type consistency: `judge_claims_llm`, `_judge_providers`, `score_answer`, `verify_answer` signatures match across phases; `ClaimResult(claim,label,score)` used consistently.
- [ ] Frequent commits: one per phase.

## Out of scope

- Retrieval technique changes (exhausted; not the bottleneck). Retrieval-v3 + rechunk-titles plans are deleted.
- Generation-model upgrade (7B→70B). Worth measuring **after** the guard is trustworthy, since the guard was corrupting every correctness number.
- Re-baselining the contaminated `eval_set_v2` retrieval benchmark.
