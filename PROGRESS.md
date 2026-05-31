# PROGRESS.md — AgroAdvisor AR

> **Single source of truth for "where are we / what's been tried."** Read this BEFORE
> writing any plan so we don't re-propose dead ends. Update it after every session
> with code changes (alongside CLAUDE.md + status-bar + memory).
>
> **Last updated:** 2026-05-31
> Companion docs: `CLAUDE.md` (Priorities), `docs/status-bar.md` (% rollup),
> `~/.claude/.../memory/project_eval_contamination.md` (why the retrieval metric lies).

---

## TL;DR — current state

- **Prod: LIVE (2026-05-30).** Frontend Vercel `agroadvisor-eta.vercel.app` → API proxy →
  backend HF Spaces `whoisluwah-agroadvisor-backend.hf.space`.
- **CITATION GUARD OVERHAUL = SHIPPED + merged to `main` 2026-05-31.** Backend redeployed to HF.
  The broken MiniLM NLI judge is retired from the hot path; an **LLM-as-judge** (provider chain)
  now scores groundedness, suppression is **surgical + rate-safe**, and `Document N:` scaffolding
  is killed at the prompt source. **Effect (local-Qwen gen + Gemini judge, gte, n=9): suppression
  11% (was ~67% on the broken NLI), faithfulness 88.9%, confidence_score 0.64–1.00 mean.** Full
  backend suite 93 pass / 1 pre-existing stale fail.
- **Generation-model upgrade (7B→70B) is now UNBLOCKED** — the guard no longer corrupts correctness
  numbers, so a prod-like 70B eval (Groq Dev/paid tier) is the next real quality lever.

### Why the guard mattered (historical, keep for NIW/arXiv honesty)
A live end-to-end trace (2026-05-31) proved the guard — not retrieval, not generation — was
producing the bad responses: retrieval returned gold in top-5 and Groq generated a correct grounded
answer, but the NLI (`nli-MiniLM2-L6-H768`) labeled 7/8 true claims `CONTRADICTED` and `score_answer`
hard-zeroed the whole advisory → blank body, "Low". **Implication: every ~40%-correctness / "Low"-floor
number measured WITH the old guard on was corrupted.** Full write-up: memory `project-guard-root-cause`.

---

## ✅ Guard overhaul — what shipped (Phases 1–6, TDD, subagent-driven)

1. **Phase 1** (`3a0cd8a`) — lexical-contradiction guard: never honor a CONTRADICTED label when the
   claim shares ≥0.6 content-token overlap with a chunk (`LEXICAL_CONTRADICTION_GUARD`).
2. **Phase 2** (`8eee998`, fix `f5457b4`) — **LLM-as-judge groundedness** (`judge_claims_llm`,
   `GROUNDEDNESS_JUDGE=llm` default); MiniLM NLI kept only as offline fallback (run off the event loop).
3. **Phase 3** (`cd30cd0`) — surgical suppression: drop the contradicted claim and mean the rest;
   full-suppress ONLY when a contradiction is safety-critical (names a rate/unit/number — `_SAFETY_CRITICAL_RE`).
4. **Phase 4** (`4ba97fc`) — thresholds env-overridable (`GUARD_SUPPRESSION_THRESHOLD`/`GUARD_ESCALATION_THRESHOLD`).
   Calibration: LLM-judge scores shifted UP to 0.64–1.00 mean (poultry 1.00, rice 0.85, soybeans 0.64);
   **kept defaults 0.2/0.4** (now cut only the genuine bottom tail — 11% suppression ≈ bottom decile).
5. **Phase 5** (`e2ca0d1`) — cite retrieved docs by bracketed title (no `Document N:` in the prompt);
   scrub residual `Document N:` from displayed citation titles + cause/action/summary prose in `rag.py`.
6. **Phase 6** — config audit: local `.env` was **legacy `agroar-prod` (MiniLM) + contaminated fine-tune
   embedder** → **FIXED to `agroar-prod-gte` + `thenlper/gte-base`** (gte retrieval verified, gold in top-5).

Plan (executed): `docs/superpowers/plans/2026-05-31-citation-guard-overhaul.md`.
Diagnostic scripts kept in `evals/`: `trace_retrieval.py`, `trace_generation.py`, `trace_pipeline_batch.py`.

### ▶▶ RESUME HERE (next session)
1. **⚠️ OWNER ACTION — verify HF Space env** (couldn't check from local; not authed to the Space).
   HF Space → Settings → Variables/Secrets: confirm `PINECONE_INDEX_NAME=agroar-prod-gte` and
   `EMBEDDING_MODEL_PATH=thenlper/gte-base`. (Owner confirmed both keys present 2026-05-31; values not yet verified.)
2. **Prod-like 70B answer eval** (now unblocked) when Groq Dev/paid tier is available — the real next lever.
3. **Re-ingest / cut over gte WITH title+section metadata** so the title-match guard validates real
   citations (the live `agroar-prod-gte` index stores only `{text, namespace}` → `(no title meta)`).
4. **Known calibration item:** `_SAFETY_CRITICAL_RE` matches a bare digit, so a CONTRADICTED claim
   mentioning a growth stage (V3/R5) full-suppresses (fail-safe but conservative) — tighten with data if it fires.

---

## ⭐ Pinned: the WINNING prod config (do not regress)

Best of everything tested (`answer_eval_full --provider local`):

| Knob | Value | Note |
|---|---|---|
| Index | `agroar-prod-gte` | gte-base 768-dim, ~20,546 vectors |
| Chunking | **512 CHARACTERS** (`ingestion/chunker.py`, `length_function=len`) | NOT tokens (token-chunking regressed — see rejected table) |
| Retrieval | dense-only, top-5 | |
| Reranker | **OFF** | |
| Embedder | `thenlper/gte-base` | `EMBEDDING_MODEL_PATH` env |
| Generation | Groq `llama-3.3-70b` (prod) / local Qwen-7B (free eval) | |
| Groundedness judge | LLM-as-judge (`GROUNDEDNESS_JUDGE=llm`) | NLI offline fallback only |

Run prod-config eval:
`EMBEDDING_MODEL_PATH=thenlper/gte-base PINECONE_INDEX_NAME=agroar-prod-gte python evals/{eval_runner,answer_eval}.py`

---

## ❌ Retrieval levers TESTED and REJECTED — STOP re-proposing these

All measured, all lost to the winning config above. Retrieval mechanics are **exhausted** and were
**never the bottleneck** (the guard was).

| Lever | Result | Verdict |
|---|---|---|
| **Token-chunking** (480 tok vs 512 char) | corr 40→35, faith 82→70 | ❌ REGRESSION — **REVERTED `f07b523`**. Do not reintroduce. |
| **Hybrid BM25+dense+RRF** | dense 0.275 → 0.245 | ❌ WORSE — queries are semantic paraphrases, weak lexical overlap |
| **Query rewrite** (slang→formal) | hit@5 0.275 → 0.280 | ❌ WASH |
| **HyDE** | hit@5 0.275 → 0.180 | ❌ WORSE |
| **Reranker** (ms-marco-MiniLM) | 40%/82.5% → 30%/70% | ❌ REGRESSION — web-trained, domain-mismatched on ag text |

**Meta-conclusion:** 4 orthogonal interventions all flat on recall@20 (~0.46) ⇒ the **single-gold
retrieval metric is a broken ruler** (relevance-judged was ~0.63), and answer-eval used local Qwen-7B
not prod Groq-70b ⇒ 40% is pessimistic vs prod. Absolute numbers unreliable; relative deltas valid.

Reusable measurement harness kept in `evals/`: `eval_retrieval_matrix.py` (compares dense/sparse/hybrid),
`remap_eval_set.py`, `filter_eval_by_section.py`, `eval_v3_ablation.py`, `audit_retrieval_v3_failures.py`,
`hybrid_core.py`. (Abandoned contextual-chunk experiment + its corpus/index were deleted 2026-05-31 — lost to the 512-char baseline.)

---

## ✅ Recently shipped (earlier this arc)

- `f553863` GENERAL_AG zero-retrieval fix — fan-out across crop namespaces (prod-verified 0→5 docs)
- `fe25f28` (1A) title-match guard skips titleless gte index → defers to NLI (un-floors confidence)
- `85986c9` split `AdvisoryDraft` (LLM) vs `AdvisoryResponse` (guard fields) — fixed hallucinated
  verifications + gen crashes on enum typos

---

## ▶ NEXT — the REAL levers (evidence-ranked, NOT retrieval technique)

1. **Generation model 7B → 70B** — biggest unmeasured correctness lever. Eval uses local Qwen-7B; prod
   is Groq-70b. **Blocked:** Groq free 70b TPD (100k/day) exhausted ⇒ needs Groq Dev paid tier.
2. **Corpus-coverage audit** — 88.9% faithful but only ~40% correct ⇒ the precise answer (rates/products)
   may simply not be IN the corpus. Audit which gold answers have a supporting chunk at all.
3. **Trustworthy eval** — prod-70b generation + a better/human judge before any more optimization.

---

## Known issues / housekeeping

- **Stale test:** `test_citation_guard_v2.py::test_verifiable_text_includes_all_advisory_fields` asserts
  warnings in verifiable text; code excludes them by design. Pre-existing, unrelated.
- **Groq key rotation** — leaked in a transcript; owner handling.
- Delete unused Pinecone indexes when sure: `agroar-prod-multilingual`, legacy `agroar-prod` (MiniLM).

---

## Non-negotiables (from CLAUDE.md)

- Commits: Conventional Commits. **NEVER** `Co-Authored-By` — Taiwo Jegede sole author (NIW).
- Do NOT report the invalid fine-tune MRR 0.6565 (train-on-test) in NIW/arXiv. Honest held-out ~0.18.
- Update CLAUDE.md + status-bar + memory + **this file** after every code-change session.
