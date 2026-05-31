# PROGRESS.md — AgroAdvisor AR

> **Single source of truth for "where are we / what's been tried."** Read this BEFORE
> writing any plan so we don't re-propose dead ends. Update it after every session
> with code changes (alongside CLAUDE.md + status-bar + memory).
>
> **Last updated:** 2026-05-31
> Companion docs: `CLAUDE.md` (Priorities), `docs/status-bar.md` (% rollup),
> `~/.claude/.../memory/project_answer_quality.md` (full eval tables),
> `project_eval_contamination.md` (why the retrieval metric lies).

---

## TL;DR — current state

- **Prod: LIVE + smoke-tested (2026-05-30).** Frontend Vercel `agroadvisor-eta.vercel.app`
  → API proxy → backend HF Spaces `whoisluwah-agroadvisor-backend.hf.space`.
- **Current focus = research: lift answer correctness off ~40%, confidence off the "Low" floor.**
- **Retrieval mechanics are EXHAUSTED** — 5 levers tested, ALL rejected (table below).
  The deployed config wins. **Do not re-propose retrieval-technique changes** without
  reading the "Rejected" table first.
- **Real next levers are NOT retrieval technique** (see "Next" below).

### ▶▶ RESUME HERE (next session)
1B title-metadata index is **BUILT** (`agroar-prod-gte-v2`, clean, retrieval no-regression).
**Only task left = gated prod cutover, BLOCKED on Groq TPD** (needs an answer-eval to confirm
confidence un-floors). When Groq generation is available: run the answer-eval A/B (old vs v2),
then flip HF `PINECONE_INDEX_NAME=agroar-prod-gte-v2`. Full steps:
`docs/superpowers/plans/2026-05-30-retrieval-rechunk-titles.md`.

---

## ⭐ Pinned: the WINNING prod config (do not regress)

Measured best of everything tested (`answer_eval_full --provider local`, n=20 seed 7):
**40% correctness / 82.5% faithfulness / 5% suppression.**

| Knob | Value | Note |
|---|---|---|
| Index | `agroar-prod-gte` | gte-base 768-dim, 20,546 vectors |
| Chunking | **512 CHARACTERS** (`chunker.py`, `length_function=len`) | NOT tokens — see rejected table |
| Retrieval | dense-only, top-5 | |
| Reranker | **OFF** | |
| Embedder | `thenlper/gte-base` | `EMBEDDING_MODEL_PATH` env |
| Generation | Groq `llama-3.3-70b` (prod) / local Qwen-7B (free eval) | |

Run prod-config eval:
`EMBEDDING_MODEL_PATH=thenlper/gte-base PINECONE_INDEX_NAME=agroar-prod-gte python evals/{eval_runner,answer_eval}.py`

---

## ❌ Retrieval levers TESTED and REJECTED (2026-05-30)

**STOP re-proposing these. All measured, all lost to the winning config above.**

| Lever | Result | Verdict | Evidence |
|---|---|---|---|
| **Token-chunking** (480 tok vs 512 char) | corr 40→**35**, faith 82→**70** | ❌ REGRESSION — **REVERTED `f07b523`** | bigger chunks = fuzzier embeddings → less precise retrieval for fact lookups |
| **Hybrid BM25+dense+RRF** | dense 0.275 → hybrid **0.245** | ❌ WORSE | BM25 unique-rescue only +0.03; queries are semantic paraphrases, weak lexical overlap |
| **Query rewrite** (slang→formal) | hit@5 0.275 → 0.280 | ❌ WASH | recall@20 gap (0.46) didn't close |
| **HyDE** (hypothetical-answer embed) | hit@5 0.275 → **0.180** | ❌ WORSE | |
| **Reranker** (ms-marco-MiniLM) | 40%/82.5% → **30%/70%** | ❌ REGRESSION | web-trained, domain-mismatched on ag text |

**Meta-conclusion:** 4 orthogonal interventions all flat on recall@20 (~0.46) ⇒ the
**single-gold retrieval metric is a broken ruler** (relevance-judged was ~0.63). And
the answer-eval uses local Qwen-7B, not prod Groq-70b ⇒ 40% is **pessimistic vs prod**.
Two confounds = absolute numbers unreliable; relative deltas valid.

**Artifacts left in tree from this research (reusable, not shipped):**
- `evals/remap_eval_set.py` + `evals/eval_set_v2_remap.jsonl` (200 items) — deterministic gold remap, no LLM
- `evals/hybrid_core.py`, `evals/eval_hybrid.py`, `evals/eval_query_expansion.py` — offline spikes
- `ingestion/ingest_en_gte.py` — rebuilds gte from raw PDFs **with title metadata** (kept, `a34d4d3`)
- Pinecone index `agroar-prod-gte-v2` — **REBUILT CLEAN 2026-05-31**: 512-char chunks + `document_title` metadata, 20,546 vectors (rice 16126 / soybeans 4077 / poultry 343). (Earlier build was token-chunks; deleted + rebuilt — had caught ~8k stale token vectors polluting it.) **Retrieval eval: hit@5 0.25 = baseline, NO regression** (titles don't move retrieval, as predicted). **NOT cut over** — gated on answer-eval (Groq TPD).
- `chunker.py` — **back to 512-char** after revert (`f07b523`). Token version was `d416d77`.
- Stale test file `backend/tests/test_chunker_tokenization.py` — does NOT exist (died with revert)

---

## ✅ Recently shipped (this research arc)

- `f553863` GENERAL_AG zero-retrieval fix — fan-out across crop namespaces (prod-verified 0→5 docs)
- `fe25f28` (1A) title-match guard skips titleless gte index → defers to NLI (un-floors confidence)
- `85986c9` split `AdvisoryDraft` (LLM) vs `AdvisoryResponse` (guard fields) — fixed hallucinated verifications + gen crashes on enum typos
- `1c8791d` reranker test coverage

---

## ▶ NEXT — the REAL levers (evidence-ranked, NOT retrieval technique)

1. **Generation model 7B → 70B** — biggest unmeasured correctness lever. Eval uses
   local Qwen-7B; prod is Groq-70b. **Blocked:** Groq free 70b TPD (100k/day) exhausted.
   ⇒ needs **Groq Dev paid tier** (owner decision: "free now, paid OK later").
2. **Corpus-coverage audit** — 82% faithful + only 40% correct ⇒ the precise answer
   (rates/products) may simply not be IN the corpus. Audit which gold answers have a
   supporting chunk at all.
3. **Trustworthy eval** — prod-70b generation + a better/human judge, before any more
   optimization. Current single-gold retrieval metric + 7B-judge both mislead.

**1B — BUILT 2026-05-31 (cutover PENDING, gated on Groq TPD):** re-ingested gte WITH
`document_title` metadata on `agroar-prod-gte-v2` keeping the **winning 512-char chunking**
→ retrieval flat (hit@5 0.25, no regression, as predicted: titles aren't embedded).
Remaining = the gated prod cutover: flip HF `PINECONE_INDEX_NAME=agroar-prod-gte-v2` once an
answer-eval confirms confidence un-floors off "Low" — **blocked on Groq TPD reset / paid tier**
(answer-eval needs generation). Plan: `docs/superpowers/plans/2026-05-30-retrieval-rechunk-titles.md` (pruned to live steps). Rollback = revert env to `agroar-prod-gte`.

---

## Known issues / housekeeping

- **Stale test:** `test_citation_guard_v2.py::test_verifiable_text_includes_all_advisory_fields`
  asserts warnings in verifiable text; code excludes them by design. Pre-existing, unrelated.
- **Groq key rotation** — leaked in a transcript; owner handling.
- Delete unused Pinecone indexes when sure: `agroar-prod-gte-v2`, `agroar-prod-multilingual`, legacy `agroar-prod` (MiniLM).

---

## VERDICT on `docs/.../2026-05-30-retrieval-rechunk-titles.md`

**Largely already executed; its core (token-chunking, Task 1) was reverted as a measured
regression.** Tasks 2 (title ingest) + 3 (remap) are in the tree. Do **not** `/build` this
plan as-is — it would re-introduce the `f07b523` regression. Only the **title-metadata,
char-chunking-preserved** slice is still worth doing (= 1B above).

---

## Non-negotiables (from CLAUDE.md)

- Commits: Conventional Commits. **NEVER** `Co-Authored-By` — Taiwo Jegede sole author (NIW).
- Do NOT report the invalid fine-tune MRR 0.6565 (train-on-test) in NIW/arXiv. Honest held-out ~0.18.
- Update CLAUDE.md + status-bar + memory + **this file** after every code-change session.
