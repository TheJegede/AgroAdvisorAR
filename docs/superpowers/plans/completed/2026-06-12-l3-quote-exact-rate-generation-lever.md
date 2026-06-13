# L3 "Quote the Exact Rate/Product" Generation Lever — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or
> superpowers:executing-plans) to implement task-by-task. Steps use `- [ ]` for tracking.

**Goal:** Cut GEN_SPECIFICITY failures — items where retrieval surfaced the right document
but the model states the *wrong number/product*. The 2026-06-12 corpus-gap split found this
is the **dominant** failure (6 of 10 failures L2-on; soybeans 5/5), NOT corpus coverage.
Fix the generation step so it reproduces the rate/product/threshold *verbatim* from the
cited chunk instead of paraphrasing or rounding.

**Evidence driving the design (read `docs/superpowers/findings/2026-06-12-corpus-gap-findings.md`):**
- GEN_SPECIFICITY dominates; RETRIEVAL_MISS is only ~1/3 of failures → generation lever, not corpus.
- **L1 (bare prompt directive `CONDITIONAL_RULE_BLOCK`) was a measured NO-OP** (0.429→0.429).
- **L2 (worked few-shot exemplars `FEW_SHOT_EXEMPLARS`) was the WIN** (corr 15%→30% paired).
- Lesson: exemplars that SHOW the behavior move the needle; directives that only TELL do not.
- **Schema-field risk:** `backend/models/advisory.py:35-44` documents that exposing extra
  LLM-filled fields made the model hallucinate/crash structured output and drop advisories.
  Therefore the schema route (Stage 2) is gated behind Stage-1 measurement, not built blind.

**Strategy — HYBRID STAGED (gated):**
- **Stage 1 (cheap, low-risk):** a `L3_VERBATIM_RATE_BLOCK` directive **plus a worked
  exemplar** showing a verbatim rate copy (L2-style, the technique that actually worked).
  Measure one paired A/B eval. If it moves GEN_SPECIFICITY/correctness → DONE.
- **Stage 2 (only if Stage 1 ≈ no-op):** add an optional verbatim `source_quote` to each
  `Product` + a **zero-cost grounding check** (the rate/quote string must appear in a
  retrieved chunk; if not → downgrade confidence / flag). Makes specificity *verifiable*.

**Tech stack:** Python, `backend/utils/prompt.py`, `backend/models/advisory.py`,
`backend/services/rag.py` (guard/post-process), pytest. Measurement reuses
`evals/answer_eval_full.py` (paired, `--provider deepinfra --sample 20 --seed 7`) and the
new `evals/retrieval_precision.py` split to confirm GEN_SPECIFICITY shrank.

**Cost discipline:** all code + unit tests are $0. The ONLY paid steps are the two paired
evals (Stage-1 measure, Stage-2 measure), each ≈ $0.01–0.02 — explicitly OK-gated.

---

## File Structure
- **Modify `backend/utils/prompt.py`** — add `L3_VERBATIM_RATE_BLOCK` + a worked verbatim
  exemplar; append in `build_system_prompt` (both intents), behind an env flag so paired
  A/B is a clean toggle.
- **Create `backend/tests/test_prompt_l3.py`** — unit tests: block present when flag on,
  absent when off; exemplar contains a verbatim-copy demonstration.
- **(Stage 2 only) Modify `backend/models/advisory.py`** — add `source_quote: str | None`
  to `Product` (optional, backwards-compatible).
- **(Stage 2 only) Modify `backend/services/rag.py`** — zero-cost grounding check of each
  product's rate/source_quote against retrieved chunk text; downgrade/flag on miss.
- **(Stage 2 only) Modify frontend `AdvisoryCard.jsx`** — render the source quote (small,
  muted) so the verbatim rate is visible/auditable; add a vitest.
- **Modify `PROGRESS.md`** + project memory — record the measured result + decision.

---

### Task 1 (Stage 1): Add the directive + verbatim exemplar, flag-gated (TDD)

**Files:** Modify `backend/utils/prompt.py`; Create `backend/tests/test_prompt_l3.py`

- [ ] **Step 1: Write failing tests**
  - `build_system_prompt(..., )` includes the L3 block + verbatim exemplar when
    `os.environ.get("L3_VERBATIM_RATE")=="1"`; excludes both when unset/`"0"`.
  - Assert the exemplar literally demonstrates copying a rate string verbatim (e.g. the
    exemplar's `rate` value equals a substring of its own "Retrieved Context" line).
  - Run: `cd backend && pytest tests/test_prompt_l3.py -v` → FAIL (block not defined).

- [ ] **Step 2: Implement**
  - Add near `CONDITIONAL_RULE_BLOCK`:
    ```python
    L3_VERBATIM_RATE_BLOCK = """VERBATIM RATES AND PRODUCTS — COPY, DO NOT PARAPHRASE:
    When the cited context states a numeric rate, product name, threshold, or interval,
    reproduce that exact string character-for-character in products_rates and key_points.
    - Never round, convert units, or paraphrase a rate (write "1.6 pt/A", not "about 1.5 pt").
    - Use the product name exactly as written in the chunk (brand + formulation).
    - If two chunks give different numbers, report the one from the cited document and say so.
    - If the context does not state a number, say it is not specified — never invent one."""
    ```
  - Add ONE worked exemplar (append to `FEW_SHOT_EXEMPLARS` or a sibling
    `L3_VERBATIM_EXEMPLAR`) whose "Retrieved Context" contains a specific rate and whose
    output `products_rates[].rate` is the **identical** string — modeling the copy.
  - In `build_system_prompt`, gate append on `os.environ.get("L3_VERBATIM_RATE")=="1"`.
    (Import `os` at top.) Keep default OFF so prod is unchanged until measured.
  - Run tests → PASS.

- [ ] **Step 3: Commit** — `feat(prompt): L3 verbatim-rate directive + exemplar (flag-gated, off by default)`

---

### Task 2 (Stage 1): Measure — paired A/B eval (PAID, OK-gated)

- [ ] **Step 1: State cost, get OK.** One paired run = 2× n=20 DeepInfra ≈ $0.02–0.04 total.
- [ ] **Step 2: Run paired**, identical 20 items seed=7, on `agroar-prod-gte-v3`:
  - B (off): `L3_VERBATIM_RATE` unset → `python evals/answer_eval_full.py --provider deepinfra --sample 20 --seed 7 --dump evals/_out_v3_L3off.jsonl`
  - A (on): `L3_VERBATIM_RATE=1 python evals/answer_eval_full.py --provider deepinfra --sample 20 --seed 7 --dump evals/_out_v3_L3on.jsonl`
  - **Apply L3 ON TOP of current prod (L2 on)** — this lever stacks, it does not replace L2.
- [ ] **Step 3: Re-run the split on both dumps** to see GEN_SPECIFICITY move:
  - `python -m evals.retrieval_precision --dump evals/_out_v3_L3on.jsonl --out evals/_retrieval_split_L3on.jsonl`
  - Compare GEN_SPECIFICITY / correctness vs the L2-on baseline (OK=10, GEN_SPECIFICITY=6).
- [ ] **Step 4: Decision gate.**
  - If correctness rises AND GEN_SPECIFICITY drops (paired, helped > hurt): **lever works →
    flip default ON** (set `L3_VERBATIM_RATE=1` in env/`build_system_prompt` default),
    skip Stage 2. Record + commit + PROGRESS.
  - If ≈ no-op (like L1): proceed to Stage 2.

---

### Task 3 (Stage 2 — ONLY if Stage 1 no-op): verifiable `source_quote` + grounding check (TDD)

**Files:** `backend/models/advisory.py`, `backend/services/rag.py`,
`backend/tests/test_l3_grounding.py`

- [ ] **Step 1: Failing tests** for a pure helper `rate_is_grounded(rate, source_quote,
  chunk_texts) -> bool` — True iff the normalized rate/quote substring appears in any
  retrieved chunk text. Cover: exact hit, whitespace/case variation, absent → False.
- [ ] **Step 2: Schema** — add `source_quote: str | None = None` to `Product`
  (`models/advisory.py`). Optional + defaulted → backwards-compatible with stored rows and
  with the structured-output draft. Update the prompt exemplar to fill `source_quote` with
  the verbatim chunk sentence. **Watch the documented risk** (advisory.py:35-44): if adding
  the field destabilizes structured output (crashes/hallucinated quotes), make it a
  post-hoc *extraction* the guard fills, not an LLM-authored field — fall back accordingly.
- [ ] **Step 3: Grounding check** in `rag._postprocess` (next to the citation guard): for
  each `products_rates[i]`, if `rate_is_grounded(...)` is False → drop/flag that rate and
  downgrade confidence (reuse existing `GUARD_*` downgrade path; do NOT blank the whole
  advisory — surgical, like the rate-safe suppression already in place). Zero LLM cost.
- [ ] **Step 4: Frontend** — render `source_quote` muted under each rate in
  `AdvisoryCard.jsx` (+vitest). Skip if `null`. EN/ES safe (verbatim quote stays source-lang;
  note it in the ES translate-bridge so the number/quote is preserved, not translated).
- [ ] **Step 5: Backend + frontend suites green**, `npm run lint`. Commit per sub-step.

---

### Task 4 (Stage 2): Measure + decide (PAID, OK-gated)
- [ ] Same paired protocol as Task 2 with the schema+check in place
  (`evals/_out_v3_L3v2on.jsonl`). Confirm GEN_SPECIFICITY drops and no correctness/faith
  regression from the grounding downgrades. Flip default ON if it wins.

---

### Task 5: Record + decide next
- [ ] Update `PROGRESS.md` (dated section, top): measured Δ, which stage shipped, default
  flag state, and whether GEN_SPECIFICITY is now the ceiling or a new label dominates.
- [ ] Update project memory (`project_l1_conditional_lever.md` — it tracks the lever series;
  add L3 result; flip "NEXT lever").
- [ ] No `backend/**`? — backend DOES change here, so pushing `main` WILL trigger the HF
  deploy Action. Confirm intent before push; verify tests green first.

---

## Self-Review notes (for the executor)
- **Stage 1 is directive + EXEMPLAR, never a bare directive** — bare directives no-op'd in L1.
- **L3 stacks on L2**, it does not replace it. Measure with L2 ON in both arms.
- **Flag-gate everything** so A/B is a clean env toggle and prod stays unchanged until a win.
- **Stage 2 schema risk is real** (advisory.py:35-44) — if `source_quote` destabilizes
  structured output, switch to guard-side extraction. Do not force a fragile field.
- **Grounding check must be surgical** — downgrade/flag the bad rate, never blank a correct
  advisory (the guard-over-suppression problem is already solved; don't reopen it).
- **This is a NEW, un-rejected lever** — it does NOT touch retrieval technique (BM25/HyDE/
  reranker, all rejected) and does NOT propose corpus re-ingest (the split ruled that out).
