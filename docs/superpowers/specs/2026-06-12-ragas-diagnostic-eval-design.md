# RAGAS Diagnostic Eval — Design Spec

> **Status: DESIGN — awaiting user review before writing-plans.**
> **Date:** 2026-06-12
> **Topic:** Add RAGAS as a standalone, offline diagnostic eval to complete the
> retrieval×generation measurement matrix and (Phase 2) escape contaminated gold.

---

## 1. Purpose & Framing

**Why:** The current bespoke eval (`evals/answer_eval_full.py`) measures only
`correctness` + `faithfulness` via a single LLM-judge. Two of the standard RAG
measurement cells have **never** been filled:

- **Generation axis:** `answer_relevancy` (does the answer address the question?) — never measured.
- **Retrieval axis:** `context_precision` / `context_recall` — only ever approximated via doc-title hit@5 + an artifact audit, never the standardized instrument.

RAGAS provides standardized, paper-citable metrics across both axes.

**What this is — and is NOT:**

- ✅ A **diagnostic instrument**: completes the measurement matrix, gives
  recognized metrics for the NIW/arXiv write-up, and (Phase 2) a path off
  contaminated gold labels.
- ❌ **NOT a lever.** RAGAS will *not* raise the faithfulness (~≤67%) or
  correctness (~≤37%) ceilings. It explains them; it does not move them. Levers
  (model swap, prompt, data) move numbers; eval frameworks measure them.

**Hard guardrails:**

1. **RAGAS is eval-only.** It lives entirely in `evals/`, is run by hand, and is
   **never imported by `rag.py`, never in the request path, never near
   `citation_guard_v2`.** Production (guard, `confidence_score`, suppression)
   behaves identically with or without it. Zero collision — confirmed by reading
   the guard code: the runtime safety gate and the offline measurement tool live
   on different planes and stay there.
2. **Cost discipline.** State paid-token cost (Gemini-flash judge × n=40 × metrics
   + the gen re-run) and get an explicit OK before the single real run.

**Circularity caveat (the NIW landmine):** RAGAS faithfulness/answer_relevancy are
themselves LLM-judged. They are a *second estimate of the same concept*, not ground
truth. If Phase 2 generates ground truth with an LLM **and** judges with an LLM, a
reviewer will call it circular (same risk family as the train-on-test MRR 0.65
incident). Phase 2 therefore **requires** a human-validated subset before any
number carries a paper claim.

---

## 2. Scope (decided)

| Decision | Choice |
|----------|--------|
| Structure | **Two phases.** Phase 1 = metric matrix (build now). Phase 2 = synthetic ground-truth (plan later). |
| Phase 1 metrics | `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`. |
| `answer_correctness` | **Deferred to Phase 2** — needs gold reference answers we do not have. |
| Data source | **Capture-enabled run** (existing dumps lack `answer` + `contexts` — see §4). |
| Module shape | **Standalone** `evals/ragas_eval.py`; does not modify the existing judge logic. |
| Judge backend | RAGAS LLM = **Gemini 2.5-flash** (the existing independent judge). |
| Embedder | **Local gte-base** (`backend/services/embedding.py`) wrapped as a LangChain `Embeddings` — $0. |
| Guard calibration cross-analysis | **Out of scope** (dropped as YAGNI). |

---

## 3. Pending Issues Discovered (reality check)

Verified against the actual files before committing to the design:

- **🔴 Issue 1 — existing dumps are unusable as-is.** `evals/_out_clean_indepjudge*.jsonl`
  schema = `namespace, lang, query, suppressed, correctness, faithfulness,
  confidence_score, corr_rationale, faith_rationale, citations`. **No `answer`
  text, no retrieved `contexts`.** RAGAS requires both. → Phase 1 needs a
  capture-enabled run (§4), not dump-reuse.
- **🔴 Issue 2 — no gold reference *answers*.** `evals/eval_set_v2_clean.jsonl`
  schema = `query, chunk_id, chunk_text, document_title, namespace`. That is a
  *retrieval* gold (which chunk), not an *answer* gold (no reference prose).
  → `answer_correctness` cannot run (deferred to Phase 2). `context_recall`
  survives by using gold `chunk_text` as `reference_contexts` (§5).
- **🟢 Issue 3 — RAGAS ↔ `langchain>=1.0.0` compatibility (VERIFIED CLEAN 2026-06-12).**
  `pip install --dry-run ragas` against the local env resolves with **no conflict and
  no downgrade**: `langchain 1.2.15`, `langchain-core 1.4.0`, `langchain-community 0.4.1`,
  `langchain_openai 1.1.15` all already-satisfied/kept. ragas 0.4.3 declares its langchain
  deps unpinned (no upper bound). Net-new installs only: `ragas-0.4.3, instructor,
  scikit-network, diskcache, docstring_parser, fsspec, jiter`. Consequences:
  (a) no isolated venv needed; (b) **ragas is an eval-only dependency — it does NOT go in
  `backend/requirements.txt` or the HF Docker image** (production image + deploy stay
  untouched); add it to an evals-side requirement only. Task 0 downgraded from gating
  kill-risk to a quick **import smoke-test** (`import ragas` + a 1-item metric run).
- **🟢 Rice gold contamination (known).** 58% of rice fails were
  GOLD_ARTIFACT/MISLABEL. Reference-based cells for the rice subset are flagged
  **provisional** in Phase 1; Phase 2 synthetic gold un-provisionals them.

---

## 4. Phase 1 — Components

Two units, clean boundary.

### 4.1 Capture extension (`evals/answer_eval_full.py`)

- Extend the per-item dump to **also persist**:
  - `answer` — the user-facing advisory prose (the harness already derives this
    via `_summarize_advisory`).
  - `contexts` — the list of retrieved chunk texts the model actually saw.
- Small, additive change; existing fields and judge behavior unchanged.
- Reusable forever — permanently closes the data gap (Issue 1) for all future evals.
- **Re-run n=40 once** to produce a capture-enabled dump. Gen-token cost quoted
  and OK'd first.

### 4.2 RAGAS scorer (`evals/ragas_eval.py`) — new, standalone

- **Input:** the capture-enabled dump (`answer` + `contexts` + `query` +
  `namespace` + `suppressed` + `confidence_score`).
- **Join:** gold `chunk_text` from `eval_set_v2_clean.jsonl` by `query` → supplies
  `reference_contexts` for `context_recall`.
- **Backend:** Gemini-2.5-flash as the RAGAS LLM; local gte-base as the RAGAS
  embedder (LangChain `Embeddings` wrapper).
- **Runs RAGAS** over the assembled dataset (question / answer / contexts /
  reference_contexts).
- **Output:** a per-crop (rice / soybean / poultry) + overall metrics report,
  with the **rice `context_recall` cell explicitly marked provisional**, and metrics
  **additionally segmented by `suppressed` (true/false)** so guard-suppression effects
  are not misattributed to generation (the dump already carries the `suppressed` flag).
  This is a report grouping only — it does NOT read or alter the guard.

---

## 5. Metric Matrix (Phase 1)

| Axis | Metric | Gold needed? | Notes |
|------|--------|--------------|-------|
| Generation | `faithfulness` | no | reference-free; trustworthy on every crop incl. rice |
| Generation | `answer_relevancy` | no (embeds) | the never-measured cell |
| Retrieval | `context_precision` | no (reference-free variant) | ranking quality of retrieved chunks |
| Retrieval | `context_recall` | gold `chunk_text` as `reference_contexts` | rice = **provisional** (contaminated gold) |

`answer_correctness` → Phase 2.

---

## 6. Testing

- **Unit tests** for `ragas_eval.py` against a tiny **fixture dump** with the
  **judge + embedder mocked** — no live LLM in CI, deterministic.
- Cover: dump parsing, gold-join by query, dataset assembly, per-crop
  aggregation, provisional-flagging of rice `context_recall`.
- `npm`/`pytest` conventions per repo (`evals/` is Python; pytest).

---

## 7. Cost Gate

Before the single real run, state and get OK on:

- Gemini-2.5-flash judge tokens ≈ n=40 × (faithfulness + answer_relevancy +
  context_precision + context_recall) LLM calls (answer_relevancy + faithfulness
  decompose into multiple sub-calls per item — estimate accordingly).
- Embedding calls = local gte-base = **$0**.
- Gen re-run for the capture-enabled dump (n=40, existing gen provider).

---

## 8. Phase 2 — Synthetic Ground-Truth (sketch; plan later)

- RAGAS testset generation from the v3 corpus → fresh questions + **reference
  answers**.
- **Human-validated subset** = the paper-safety gate against LLM-grading-LLM
  circularity (§1).
- Outcomes: un-provisionals rice reference-based metrics, enables
  `answer_correctness`, and provides the novelty angle.
- **Absorbs the "curate rice gold" loose end** — no separate hand-curation plan
  needed; synthetic-gen-with-human-validation does that job.

---

## 9. Open Questions / Risks

- ~~**Task 0 gating risk:** RAGAS ↔ langchain coexistence.~~ **RESOLVED 2026-06-12**
  — verified clean (see §3 Issue 3). Task 0 is now just an import smoke-test. ragas
  added as an eval-only dependency (not in `backend/requirements.txt`).
- **Post-guard answer:** RAGAS scores the *post-guard* advisory (after
  suppression / confidence downgrade) → it measures gen+guard end-to-end. The
  dump carries `suppressed`; the report **segments by `suppressed` true/false** so
  guard effects are not misattributed to generation.
- **n=40 sample size:** matrix numbers are diagnostic, not high-precision; treat
  per-crop cells (esp. small crops like poultry) as directional.
