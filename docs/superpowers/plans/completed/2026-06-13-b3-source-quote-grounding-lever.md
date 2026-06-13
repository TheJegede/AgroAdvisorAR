# B3 source_quote Grounding Lever Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional per-`Product` `source_quote` field + prompt directive/exemplar (kill-switch env, default ON) that forces the 70B to attach the verbatim retrieved sentence stating each rate, raising the rate-grounding rate (today 46% < 80%) and thus correctness/faithfulness.

**Architecture:** Mirrors the L3/B1 lever pattern (directive + worked exemplar, measured paired). `source_quote` is an internal generation scaffold — declared on `Product`, filled by the LLM, then stripped in `rag._postprocess_async` before guard/storage/display (exactly as B1's `analysis` is). Default ON via `B3_SOURCE_QUOTE` env; `=0` is the kill-switch. Stacks on L2+L3+B1. Stage 1 = directive+exemplar+field+strip (this plan). Stage 2 (verify-quote-in-chunk grounding GATE that downgrades confidence) is held — build only if Stage 1's paired delta is flat.

**Tech Stack:** Python / Pydantic (`backend/models/advisory.py`), prompt assembly (`backend/utils/prompt.py`), post-processing (`backend/services/rag.py`), pytest. Eval = `evals/answer_eval_full.py` (DeepInfra 70B + independent Gemini judge) + `evals/paired_compare.py`.

---

## Context (read before starting — from PROGRESS.md top block)

- **Baseline to beat (off-arm):** `evals/_out_clean_indepjudge_b1on.jsonl` — clean set, DeepInfra 70B, independent Gemini judge, n=40 seed=7, **corr 27.5% / faith 65.0% / supp 0%** (L2+L3+B1 all ON, B3 did not exist → it is the B3-OFF arm). This is the comparison anchor.
- **Why B3 is live, not redundant:** `evals/_b3_grounding.py` over the two-step dump found only **46% (11/24)** of stated rates are number-grounded in retrieved chunks. B1 quotes into a single `analysis` scratchpad but does NOT reliably ground each *rate* → per-rate `source_quote` is the targeted fix. (Caveat: 46% is a crude number-substring metric, treat as a floor.)
- **Schema-fragility watch (the one real risk):** B1 added an optional top-level `analysis` and saw **0 structured-output skips** at n=40. B3 adds an optional field on the **nested** `Product` model — nested schema changes are the classic `with_structured_output` failure mode (the AdvisoryDraft docstring documents past crashes on nested type/enum issues). The eval harness reports scored/skipped — **a non-zero skip count is a kill signal**, watch it.
- **Lever series:** L1 directive=NO-OP, L2 exemplars=WIN, L3 verbatim=WIN, B1 scratchpad=WIN, B2 format-tax=DISPROVEN/closed. Pattern: structural/exemplar changes move the needle, bare directives don't → B3 ships WITH an exemplar.
- **Decoupling note:** `source_quote` is stripped pre-display, so frontend `AdvisoryCard.jsx` / DB storage need **zero** changes (unknown-field-tolerant). Keep blast radius to the three backend files.

---

## File Structure

- **Modify `backend/models/advisory.py`** — add `source_quote: str | None = None` to `Product`. One field, last position, optional → backward-compatible with every stored `Product`.
- **Modify `backend/utils/prompt.py`** — add `B3_SOURCE_QUOTE_BLOCK` + `B3_SOURCE_QUOTE_EXEMPLAR` constants; append them in `build_system_prompt` behind `os.environ.get("B3_SOURCE_QUOTE", "1") != "0"`, after the B1 block.
- **Modify `backend/services/rag.py`** — in `_postprocess_async`, after the `analysis` strip, blank every `Product.source_quote` so it never reaches guard/storage/display.
- **Test `backend/tests/test_prompt_b3.py`** (new) — prompt-assembly + env-toggle unit tests.
- **Test `backend/tests/test_advisory_model.py`** (extend or create) — `Product` accepts/defaults `source_quote`.
- **Test `backend/tests/test_rag_postprocess.py`** (extend existing rag-postprocess tests; if none, new) — strip behavior.

---

### Task 1: `source_quote` field on `Product`

**Files:**
- Modify: `backend/models/advisory.py:10-14`
- Test: `backend/tests/test_advisory_model.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_advisory_model.py
from models.advisory import Product


def test_product_source_quote_defaults_none():
    p = Product(product="Sharpen", rate="3.2 pt/A", application_method="Burndown")
    assert p.source_quote is None


def test_product_accepts_source_quote():
    p = Product(
        product="Sharpen", rate="3.2 pt/A", application_method="Burndown",
        source_quote="apply Sharpen at 3.2 pt/A in the burndown",
    )
    assert p.source_quote == "apply Sharpen at 3.2 pt/A in the burndown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_advisory_model.py -v`
Expected: FAIL — `test_product_source_quote_defaults_none` errors with `AttributeError: 'Product' object has no attribute 'source_quote'` (and the accepts test fails: pydantic ignores the unknown kwarg).

- [ ] **Step 3: Write minimal implementation**

```python
# backend/models/advisory.py
class Product(BaseModel):
    product: str
    rate: str
    application_method: str
    pre_harvest_interval: str | None = None
    # B3 grounding scaffold — the verbatim retrieved sentence that states this
    # product's rate. Filled by the LLM, stripped in rag._postprocess_async
    # before guard/storage/display (internal, never shown to the farmer).
    source_quote: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_advisory_model.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add backend/models/advisory.py backend/tests/test_advisory_model.py
git commit -m "feat(b3): optional source_quote field on Product"
```

---

### Task 2: B3 prompt block + exemplar + env toggle

**Files:**
- Modify: `backend/utils/prompt.py` (add constants after `B1_REASONING_EXEMPLAR` ~line 167; append in `build_system_prompt` after the B1 block ~line 375)
- Test: `backend/tests/test_prompt_b3.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_prompt_b3.py
import os
import pytest
from utils.prompt import build_system_prompt


def _build(**over):
    kwargs = dict(
        soil_context={"available": False}, weather_context={"available": False},
        retrieved_docs=[], session_history=[], language="en",
        is_safety_critical=False, county_name="Lonoke",
    )
    kwargs.update(over)
    return build_system_prompt(**kwargs)


def test_b3_block_present_by_default(monkeypatch):
    monkeypatch.delenv("B3_SOURCE_QUOTE", raising=False)
    prompt = _build()
    assert "source_quote" in prompt
    assert "PER-RATE SOURCE QUOTE" in prompt


def test_b3_exemplar_present_by_default(monkeypatch):
    monkeypatch.delenv("B3_SOURCE_QUOTE", raising=False)
    prompt = _build()
    # exemplar models a source_quote copied verbatim from the retrieved sentence
    assert "150 lb N/A" in prompt


def test_b3_killswitch_removes_block(monkeypatch):
    monkeypatch.setenv("B3_SOURCE_QUOTE", "0")
    prompt = _build()
    assert "PER-RATE SOURCE QUOTE" not in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_prompt_b3.py -v`
Expected: FAIL — `AssertionError` ("PER-RATE SOURCE QUOTE" not in prompt); constants don't exist yet.

- [ ] **Step 3: Write minimal implementation**

Add constants after `B1_REASONING_EXEMPLAR` (after line 167):

```python
# backend/utils/prompt.py
B3_SOURCE_QUOTE_BLOCK = """PER-RATE SOURCE QUOTE — GROUND EVERY RATE:
For each entry in products_rates, fill its "source_quote" field with the single
verbatim sentence (character-for-character) from the [bracketed] retrieved context
that states that product's rate. Copy it exactly — do not paraphrase, summarize, or
stitch fragments. If no retrieved sentence states the rate, leave source_quote null
AND do not include that product in products_rates (never invent a rate). source_quote
is an internal grounding check removed before display."""

# Worked exemplar (exemplars move the needle, bare directives don't — measured
# L1/L2/L3/B1 pattern). The rate "150 lb N/A" appears in BOTH the retrieved-context
# line and the source_quote value, modeling the character-for-character copy.
B3_SOURCE_QUOTE_EXEMPLAR = """PER-RATE SOURCE-QUOTE EXAMPLE:
Retrieved Context:
[Arkansas Rice Production Handbook 2026 - Nitrogen Section] Apply 150 lb N/A in a two-way split on silt loam soils: 105 lb preflood and 45 lb at midseason.
products_rates entry (source_quote copies the rate sentence VERBATIM):
{
  "product": "Urea (silt loam, two-way split)",
  "rate": "150 lb N/A",
  "application_method": "105 lb preflood + 45 lb at midseason",
  "pre_harvest_interval": null,
  "source_quote": "Apply 150 lb N/A in a two-way split on silt loam soils: 105 lb preflood and 45 lb at midseason."
}"""
```

Append in `build_system_prompt`, immediately after the B1 block (after line 375, before `return "\n".join(parts)`):

```python
    # B3 per-rate source_quote grounding lever — forces a verbatim retrieved
    # sentence onto each products_rates entry (B1's single analysis scratchpad
    # under-grounds individual rates; rate-grounding measured 46% < 80%).
    # Default ON; set B3_SOURCE_QUOTE=0 to kill-switch. Stacks on L2+L3+B1.
    if os.environ.get("B3_SOURCE_QUOTE", "1") != "0":
        parts.append("")
        parts.append(B3_SOURCE_QUOTE_BLOCK)
        parts.append("")
        parts.append(B3_SOURCE_QUOTE_EXEMPLAR)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_prompt_b3.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/utils/prompt.py backend/tests/test_prompt_b3.py
git commit -m "feat(b3): source_quote prompt directive + exemplar, default ON"
```

---

### Task 3: Strip `source_quote` in `_postprocess_async`

**Files:**
- Modify: `backend/services/rag.py:263-266` (right after the B1 `analysis` strip)
- Test: `backend/tests/test_rag_postprocess.py` (extend; create if absent)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_rag_postprocess.py
import asyncio
from models.advisory import AdvisoryDraft, Product, ContextMeta
from services import rag


def _draft_with_quote():
    return AdvisoryDraft(
        response_type="diagnostic", problem_summary="x", confidence="High",
        confidence_explanation="x", language="en",
        context_meta=ContextMeta(soil_data_available=False,
                                 weather_data_available=False, county_fips="05085"),
        products_rates=[Product(product="Sharpen", rate="3.2 pt/A",
                                application_method="Burndown",
                                source_quote="apply Sharpen at 3.2 pt/A")],
    )


def test_postprocess_strips_source_quote():
    out = asyncio.run(rag._postprocess_async(
        _draft_with_quote(), docs=[], soil={"available": False},
        weather={"available": False}, county_fips="05085",
    ))
    assert out.products_rates[0].source_quote is None
    # the rate itself must survive the strip
    assert out.products_rates[0].rate == "3.2 pt/A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_rag_postprocess.py::test_postprocess_strips_source_quote -v`
Expected: FAIL — `assert 'apply Sharpen at 3.2 pt/A' is None` (strip not implemented).

- [ ] **Step 3: Write minimal implementation**

In `rag._postprocess_async`, after the existing `analysis` strip (line 265-266), add:

```python
    # B3: source_quote is an internal grounding scaffold — blank it on every
    # product before the guard scores prose and before storage/display, exactly
    # as the B1 analysis scratchpad is stripped above.
    if any(p.source_quote for p in result.products_rates):
        result = result.model_copy(update={
            "products_rates": [
                p.model_copy(update={"source_quote": None})
                for p in result.products_rates
            ]
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_rag_postprocess.py::test_postprocess_strips_source_quote -v`
Expected: PASS

- [ ] **Step 5: Run the full backend suite (no regressions)**

Run: `cd backend && pytest -q`
Expected: PASS — prior green count (300) + the new B3 tests, 0 failures.

- [ ] **Step 6: Commit**

```bash
git add backend/services/rag.py backend/tests/test_rag_postprocess.py
git commit -m "feat(b3): strip source_quote pre-display in postprocess"
```

---

### Task 4: Paired eval measurement + ship/kill decision

> **COST GATE.** This runs DeepInfra 70B generation + Gemini judge over n=40 (same shape as the B2 two-step run). Estimate **~$0.05–0.15 paid tokens**. **State the estimate and get Taiwo's explicit OK before running.** No prod deploy in this task — `prompt.py`/`rag.py` changes already committed are dormant unless this measurement wins (they ship on the next push to `main` that touches `backend/**` → HF deploy Action).

**Files:**
- Run: `evals/answer_eval_full.py`, `evals/paired_compare.py`
- Output: `evals/_out_clean_indepjudge_b3on.jsonl` (gitignored)

- [ ] **Step 1: Cost-gate — present estimate, get OK.** Do not proceed without it.

- [ ] **Step 2: Run the B3-ON arm** (B3 default ON; L2+L3+B1 also ON = identical to the baseline arm except B3)

Run:
```bash
cd evals && python answer_eval_full.py \
  --provider deepinfra --judge-provider gemini \
  --sample 40 --seed 7 --eval-set eval_set_v2_clean.jsonl \
  --dump _out_clean_indepjudge_b3on.jsonl
```
Expected: `scored=40 skipped=0`. **`skipped > 0` = nested-schema fragility materialized → this is a KILL signal**, record the count and the offending items; do not ship.

- [ ] **Step 3: Paired compare vs the B3-OFF baseline**

Run:
```bash
cd evals && python paired_compare.py \
  _out_clean_indepjudge_b1on.jsonl _out_clean_indepjudge_b3on.jsonl
```
Expected: prints paired corr/faith deltas + helped/hurt/same counts and per-crop corr.

- [ ] **Step 4: Re-measure rate-grounding on the B3 dump**

The dump carries `products_rates` (post-strip, so `source_quote` is null — grounding is measured on `rate` numbers vs `chunk_snippets`, same metric as the baseline). Point `evals/_b3_grounding.py` at the new dump:

Run: `cd evals && python -c "import _b3_grounding" `  — first edit its `PATH = "_out_clean_indepjudge_b3on.jsonl"`.
Expected: a grounding % to compare against the 46% baseline. A rise toward 80% is the mechanism-level confirmation B3 worked even if corr/faith are noisy at n=40.

- [ ] **Step 5: Decide — ship default ON, or kill.**

**Ship (leave default ON, commit nothing more — already committed)** if ALL hold: `skipped == 0` AND (corr OR faith improves with helped ≥ hurt) AND rate-grounding rises. Mirror the B1/L3 bar: at n=40 a small absolute corr delta is acceptable if pairing favors B3 and faith (safety metric) holds/improves.

**Kill (flip default OFF)** if `skipped > 0`, OR corr/faith regress with hurt > helped. To kill: change `"1"` → `"0"` default in the `B3_SOURCE_QUOTE` guard in `prompt.py` (so the field+exemplar stay in-tree but dormant), commit `fix(b3): default OFF — paired arm flat/negative`.

- [ ] **Step 6: Record result in PROGRESS.md + memory**

Append a B3 result block to PROGRESS.md top section (numbers, skip count, verdict, dump path) and update the `project_l1_conditional_lever` memory's lever series (`B3=WIN`/`B3=DISPROVEN`). Note whether the backend change ships on next push.

- [ ] **Step 7: Commit docs**

```bash
git add PROGRESS.md docs/superpowers/plans/2026-06-13-b3-source-quote-grounding-lever.md
git commit -m "docs(b3): source_quote lever result + verdict"
```

---

## Stage 2 (HELD — build only if Task 4 corr/faith is flat but rate-grounding clearly rose)

If the model fills `source_quote` faithfully (grounding ↑) but corr/faith don't move, the field is generated-but-unused. Stage 2 turns it into a **grounding GATE** in `_postprocess_async` (before the strip): for each product, if `source_quote` is non-null but its text does NOT appear in any `doc.page_content`, the quote is hallucinated → drop that product's rate / downgrade confidence to Low. This needs `docs` (already a `_postprocess_async` param) and a substring/normalized-match check. **Do not build pre-emptively** — only if Stage 1 evidence says the scaffold is honest but inert. Mirrors L3's Stage-1/Stage-2 structure (Stage 2 there was never needed).

---

## Self-Review

**Spec coverage:** optional field (Task 1) ✓; kill-switch env default ON (Task 2) ✓; schema-fragility/skip watch (Task 4 Step 2, explicit kill signal) ✓; measure vs `_out_clean_indepjudge_b1on.jsonl` (Task 4 Step 3) ✓; cost-gate paid runs (Task 4 Step 1) ✓; plan-before-code, TDD, frequent commits ✓.

**Placeholder scan:** none — every code/prompt/test block is literal; commands have expected output.

**Type consistency:** `source_quote: str | None = None` identical across model, prompt exemplar JSON, strip code, and tests. `B3_SOURCE_QUOTE` env key identical in prompt guard + all toggle tests. `_postprocess_async` signature matches the real one (`result, docs, soil, weather, county_fips, ...`).
