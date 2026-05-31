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

## 🔴 ROOT CAUSE FOUND (2026-05-31): the CITATION GUARD was the bottleneck — not retrieval, not generation

A live end-to-end trace localized "bad frontend responses" to the **citation guard**, which
was **deleting and flooring correct, grounded advisories**. Retrieval and generation are
**exonerated**. This reframes the entire research arc: the ~40% correctness / "Low" floor
was the guard corrupting good answers, so every retrieval/generation number measured WITH
the guard on was misleading.

**Evidence (diagnostic scripts left in `evals/`):**
- `trace_retrieval.py` — retrieval is fine: 6/6 sampled queries returned on-topic chunks, gold in top-5.
- `trace_generation.py` — generation is fine: Groq produced a correct grounded answer; guard blanked it (`confidence_score 0.0`, body emptied, "Low").
- A/B with `NLI_CITATION_GUARD_ENABLED=0` → same query returns a full, useful advisory.
- The judge is **confidently wrong**: on a rice query whose gold chunk literally contains `GPM = D x D x L`, the NLI labeled 7/8 true claims `CONTRADICTED` at prob 0.5–0.625. No threshold fixes a model this wrong.

**The three guard defects:** (A) `score_answer` hard-zeroes the whole answer on ANY
`CONTRADICTED` claim — one weak-NLI false positive nukes everything; (B) the prompt numbers
chunks `Document N:` and the LLM echoes that into citation titles, breaking exact title-match
→ confidence force-floored to "Low"; (C) decomposition emits un-entailable meta-claims
("Document 2 is related to…") feeding (A).

**▶ NEW FOCUS = fix the guard.** Plan: `docs/superpowers/plans/2026-05-31-citation-guard-overhaul.md`.

---

## TL;DR — current state

- **Prod: LIVE + smoke-tested (2026-05-30).** Frontend Vercel `agroadvisor-eta.vercel.app`
  → API proxy → backend HF Spaces `whoisluwah-agroadvisor-backend.hf.space`.
- **CITATION GUARD OVERHAUL = SHIPPED 2026-05-31** (branch `guard-overhaul`, Phases 1–6). The broken
  MiniLM NLI is retired from the hot path; an LLM-as-judge (provider chain) now scores groundedness,
  suppression is surgical (per-claim, rate-safe), and `Document N:` is killed at the prompt source.
  **Measured effect (local Qwen gen + Gemini judge, gte config, n=9): suppression 11% (1/9), faithfulness
  88.9%, confidence_score now 0.64–1.00 mean** — vs the broken NLI's 0.0/0.34/0.54. Full backend suite
  93 passed / 1 pre-existing stale fail.
- **Phase 0 SHIPPED earlier** (`f457d28`): contradiction confidence gate (Fix 1) + strip `Document N:` (Fix 2).
- **Retrieval mechanics are EXHAUSTED and were never the bottleneck** — 5 levers tested, all rejected
  (table below). Retrieval-v3 + rechunk-titles plans **DELETED 2026-05-31** (abandoned narrow path).
  Reusable measurement harness kept (`eval_retrieval_matrix`, audit, filter, ablation).
- **Generation-model upgrade (7B→70B) is now UNBLOCKED** — the guard no longer corrupts correctness
  numbers, so a prod-like 70B eval (Groq paid/Dev tier) is the next real lever.

### ✅ GUARD OVERHAUL — what shipped (branch `guard-overhaul`)
Executed `docs/superpowers/plans/2026-05-31-citation-guard-overhaul.md` via subagent-driven-development
(implementer + review per phase, TDD throughout):

1. **Phase 1** (`3a0cd8a`) — lexical-contradiction guard: never honor a CONTRADICTED label when the claim
   shares ≥0.6 content-token overlap with a chunk (`LEXICAL_CONTRADICTION_GUARD`).
2. **Phase 2** (`8eee998`, fix `f5457b4`) — LLM-as-judge groundedness (`judge_claims_llm` + `GROUNDEDNESS_JUDGE=llm`
   default); MiniLM NLI kept only as offline fallback (run off the event loop).
3. **Phase 3** (`cd30cd0`) — surgical suppression: drop the contradicted claim and mean the rest;
   full-suppress ONLY when a contradiction is safety-critical (names a rate/unit/number — `_SAFETY_CRITICAL_RE`).
4. **Phase 4** (`4ba97fc`) — thresholds env-overridable (`GUARD_SUPPRESSION_THRESHOLD`/`GUARD_ESCALATION_THRESHOLD`).
   Calibration: LLM-judge scores shifted UP to 0.64–1.00; **kept defaults 0.2/0.4** (now cut only the
   genuine bottom tail — 11% suppression ≈ bottom decile). Per-namespace: poultry conf 1.00, rice 0.85, soybeans 0.64.
5. **Phase 5** (`e2ca0d1`) — cite retrieved docs by bracketed title (no `Document N:` in the prompt);
   scrub residual `Document N:` from displayed citation titles + cause/action/summary prose in `rag.py`.
6. **Phase 6** — config audit: local `.env` was **legacy `agroar-prod` (MiniLM) + contaminated fine-tune
   embedder** → **FIXED to `agroar-prod-gte` + `thenlper/gte-base`** (gte retrieval verified, gold in top-5).

### ▶▶ RESUME HERE (next session)
1. **⚠️ OWNER ACTION — verify HF Space env** (could not check from local; not authed to the Space). In the HF
   Space → Settings → Variables/Secrets, confirm `PINECONE_INDEX_NAME=agroar-prod-gte` and
   `EMBEDDING_MODEL_PATH=thenlper/gte-base`. If they're legacy, prod is mis-served — fix them.
2. **Prod-like 70B answer eval** (now unblocked) when Groq Dev/paid tier is available — the guard no longer
   corrupts correctness numbers, so this is the next real quality lever.
3. **Re-ingest gte with title/section metadata (1B)** so the title-match guard validates real citations
   (gte index still `(no title meta)`).
4. **Known calibration item:** `_SAFETY_CRITICAL_RE` matches a bare digit, so a CONTRADICTED claim mentioning
   a growth stage (V3/R5) full-suppresses (fail-safe but conservative) — tighten with eval data if it fires.

Do **not** resume any retrieval-v3 work. Keep `agroar-prod-gte` / 512-char / dense top-5 as the retrieval baseline.

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

### Retrieval v3 plan execution — Module 0 started (2026-05-31) - Using Codex for this

Built the evaluation harness first, per
`docs/superpowers/plans/2026-05-31-retrieval-v3-architecture.md`, before any ingestion or
backend retrieval changes:

- Added `evals/eval_retrieval_matrix.py`.
- One command now compares `dense`, `sparse`, `hybrid_rrf`, and optional `hybrid_rerank`
  on the same eval set.
- Reports `hit@1`, `hit@5`, `MRR@5`, `NDCG@5`, `candidate_recall@20/30`, and
  per-namespace breakdown.
- Saves JSON results under `evals/results/`.
- Added pure unit tests in `evals/tests/test_eval_retrieval_matrix.py` so metric logic is
  covered without Pinecone/model/API dependencies.

Validation passed:

```bash
python -m pytest evals/tests/test_eval_retrieval_matrix.py evals/tests/test_hybrid_core.py
python evals/eval_retrieval_matrix.py --help
python -m compileall evals/eval_retrieval_matrix.py
```

Live matrix run against `agroar-prod-gte-v2` also completed with Pinecone/model access:

```bash
EMBEDDING_MODEL_PATH=thenlper/gte-base PINECONE_INDEX_NAME=agroar-prod-gte-v2 python evals/eval_retrieval_matrix.py --eval-set evals/eval_set_v2_remap.jsonl
```

Saved result: `evals/results/retrieval_matrix_20260531_140038.json`.

| Strategy | hit@1 | hit@5 | MRR@5 | NDCG@5 | rec@20 | rec@30 |
|---|---:|---:|---:|---:|---:|---:|
| dense | 0.090 | 0.245 | 0.148 | 0.172 | 0.430 | 0.470 |
| sparse | 0.035 | 0.115 | 0.062 | 0.075 | 0.190 | 0.200 |
| hybrid_rrf | 0.115 | 0.240 | 0.162 | 0.181 | 0.355 | 0.430 |

Interpretation: Module 0 is implemented, and the measured result reinforces the existing
finding that naive BM25+RRF is not enough. Dense v2 is still near the expected no-regression
baseline, while hybrid improves hit@1/MRR slightly but misses the v3 gate (`hit@5 >= 0.40`,
`candidate_recall@30 >= 0.65`). Next v3 work should move to section-aware/contextual corpus
work, not production cutover.

### Retrieval v3 plan execution — Module 1 section-aware corpus started (2026-05-31)

Added a section-aware extraction/chunking path without changing the live ingestion or backend
retrieval path:

- `ingestion/extractor.py` now has `extract_pages()` preserving 1-based page numbers.
- `ingestion/chunker.py` now has `chunk_sectioned_document()` plus deterministic `doc_id`,
  `parent_section_id`, page range, `doc_type`, `pub_year`, `section_heading`,
  `subsection_heading`, and contextual `retrieval_text` metadata.
- Existing `chunk_document()` remains intact for current gte/live scripts.
- Added `ingestion/build_corpus_v3.py`, which writes the v3 experiment artifact to
  `ingestion/en_chunks/corpus_v3.jsonl` (ignored by git like the existing corpus cache).
- Added `ingestion/tests/test_section_aware_chunker.py`.

Real corpus build result:

```bash
python ingestion/build_corpus_v3.py
```

Output: `21,065` chunks, `document_title` coverage `100.0%`, `section_heading` coverage
`97.1%`. The chunk count is close to the current 20,546-vector corpus, so the heading
heuristic is no longer grossly over-splitting table cells. Known caveat: some PDF header,
FAQ, and caption-like lines are still imperfectly classified as headings; acceptable for
the first v3 experiment artifact, but inspect before index cutover.

Validation passed:

```bash
python -m pytest ingestion/tests/test_section_aware_chunker.py ingestion/tests/test_ingest_gte_metadata.py
python -m compileall ingestion/extractor.py ingestion/chunker.py ingestion/build_corpus_v3.py
```

### Retrieval v3 plan execution — Module 2 contextual chunk text continued (2026-05-31)

Completed the deterministic contextual-text slice for v3 ingestion, still without changing the
live production retrieval path:

- `ingestion/chunker.py` now builds a concise `retrieval_header` for section-aware chunks:
  document title, section heading, and a short deterministic content summary with salient terms.
- Header generation filters obvious author/byline lines so the synthetic context starts with
  retrievable agricultural content instead of names where possible.
- `retrieval_text` is now `retrieval_header + source chunk`; `source_text` remains the original
  PDF chunk in the corpus artifact for citations/display.
- `ingestion/build_corpus_v3.py` writes both `retrieval_header` and `retrieval_text` alongside
  `source_text`.
- Added `ingestion/ingest_retrieval_v3.py`, which embeds `retrieval_text` into a separate
  v3 experiment index and preserves original text in
  Pinecone metadata `text`/`source_text`.
- Added `ingestion/tests/test_ingest_retrieval_v3.py`.
- Extended `evals/remap_eval_set.py` and `evals/eval_retrieval_matrix.py` so v3 can be
  remapped/evaluated against `ingestion/en_chunks/corpus_v3.jsonl` instead of the old
  production chunk IDs.

Real corpus rebuild result:

```bash
python ingestion/build_corpus_v3.py
```

Output remains `21,065` chunks, `document_title` coverage `100.0%`, and `section_heading`
coverage `97.1%`. PyMuPDF still emits one font warning for an embedded AGaramond face, but
the build completes.

Validation passed:

```bash
python -m pytest ingestion/tests/test_section_aware_chunker.py ingestion/tests/test_ingest_gte_metadata.py ingestion/tests/test_ingest_retrieval_v3.py
python -m pytest ingestion/tests/test_ingest_retrieval_v3.py evals/tests/test_eval_retrieval_matrix.py
python -m compileall ingestion/chunker.py ingestion/build_corpus_v3.py ingestion/ingest_retrieval_v3.py
python -m compileall ingestion/ingest_retrieval_v3.py evals/remap_eval_set.py evals/eval_retrieval_matrix.py
```

Index/eval result:

```bash
python ingestion/ingest_retrieval_v3.py --model thenlper/gte-base --index agroar-prod-retrieval-v3-gte
python evals/remap_eval_set.py --eval-set evals/eval_set_v2.jsonl --corpus-jsonl ingestion/en_chunks/corpus_v3.jsonl --out evals/eval_set_v2_remap_v3.jsonl
python evals/eval_retrieval_matrix.py --eval-set evals/eval_set_v2_remap_v3.jsonl --model thenlper/gte-base --index agroar-prod-retrieval-v3-gte --corpus-jsonl ingestion/en_chunks/corpus_v3.jsonl
```

Correct gte v3 index built: `agroar-prod-retrieval-v3-gte`, `21,065` vectors, 768-dim.
Saved result: `evals/results/retrieval_matrix_20260531_143239.json`.

| Strategy | hit@1 | hit@5 | MRR@5 | NDCG@5 | rec@20 | rec@30 |
|---|---:|---:|---:|---:|---:|---:|
| dense | 0.060 | 0.160 | 0.094 | 0.111 | 0.315 | 0.360 |
| sparse | 0.025 | 0.070 | 0.043 | 0.049 | 0.160 | 0.180 |
| hybrid_rrf | 0.080 | 0.155 | 0.110 | 0.121 | 0.230 | 0.300 |

Verdict: Module 2 implementation is complete, but the acceptance gate **fails** on the
single-gold remapped eval. Contextual v3 chunks underperform current dense v2/current prod
(`hit@5` roughly `0.160` vs `0.245-0.250`). Do not cut over. Next investigation should
inspect whether the deterministic section split/remap is producing overly broad or shifted
gold chunks, especially for rice (`hit@5=0.064`), before moving to Module 3.

Caveat: one accidental 384-dim Pinecone index named `agroar-prod-retrieval-v3` was created
before the ingester default was fixed; ignore/delete later. The valid index from this run is
`agroar-prod-retrieval-v3-gte`.

### Retrieval v3 Module 2 failure audit — rice first (2026-05-31)

Added `evals/audit_retrieval_v3_failures.py` to explain failed v3 retrieval rows by comparing:

- original eval gold chunk text,
- v3 remapped gold chunk/source text,
- v3 retrieval header/title/section,
- dense top-k matches from Pinecone with title/section/source previews.

Validation:

```bash
python -m compileall evals/audit_retrieval_v3_failures.py
python evals/audit_retrieval_v3_failures.py --help
```

Ran the rice audit:

```bash
python evals/audit_retrieval_v3_failures.py --original-eval evals/eval_set_v2.jsonl --remapped-eval evals/eval_set_v2_remap_v3.jsonl --corpus-jsonl ingestion/en_chunks/corpus_v3.jsonl --index agroar-prod-retrieval-v3-gte --namespace rice --limit 200
```

Saved:

- `evals/results/retrieval_v3_failure_audit_rice_20260531_144039.json`
- `evals/results/retrieval_v3_failure_audit_rice_20260531_144039.md`

Findings over all audited dense rice failures:

- Audited failures: `86` out of `110` rice eval items.
- Mean original-to-v3 gold text overlap: `0.8374`.
- Low-overlap remaps `<0.5`: `1`.
- Mean gold retrieval-header length: `204.2` chars.
- Top-1 result had the same document title as gold only `16/86` times.
- Top-1 result had the same section heading as gold only `12/86` times.
- Gold section distribution among failures is dominated by weak research-paper sections:
  `Abstract` = `28`, `Acknowledgments` = `10`, `Introduction` = `9`.
- `38/86` rice failures have gold chunks from `Abstract` or `Acknowledgments`.
- `12/86` failed rice queries mention another crop such as soybean/corn/cotton.

Interpretation:

- Bad v3 remapping is **not** the primary cause; the remapped chunks usually preserve the
  original gold text.
- The bigger issue is that the single-gold eval often points to brittle research-study chunks
  (`Abstract`, `Acknowledgments`, tables/results fragments) while dense retrieval prefers more
  generally useful Extension guidance such as handbooks, weed-control chapters, and N-ST*R docs.
- The v3 headers may still add noise, but the first-order blocker is eval/corpus target quality:
  the gold answer evidence is often a poor target for farmer-answer retrieval.

Decision:

- Do **not** proceed to Module 3 on this v3 corpus as a production candidate.
- Next improvement should be a controlled ablation plus eval cleanup:
  1. run v3 variants embedding `source_text` only vs `title | section + source_text` vs current
     header + source;
  2. separately tag/filter eval gold chunks from low-value sections (`Abstract`,
     `Acknowledgments`, `References`, table fragments) to see whether the regression is real
     retrieval loss or mostly a broken single-gold target;
  3. prefer a conservative v2.5 candidate if ablation confirms that 512-char source-text
     embeddings remain stronger.

### Retrieval v3 Module 2 ablation + eval cleanup (2026-05-31)

Confirmed the interrupted follow-up work and completed the controlled diagnostic slice:

- Added `evals/filter_eval_by_section.py` to tag/filter weak single-gold targets whose
  remapped v3 gold chunks come from brittle sections (`Abstract`, `Acknowledgments`,
  `References`) or table/results fragments.
- Added `evals/eval_v3_ablation.py` to compare local dense retrieval over the same v3
  corpus without creating new Pinecone indexes:
  `source_text`, `title_section_source`, and current contextual `retrieval_text`.
- Added focused unit coverage in `evals/tests/test_v3_diagnostics.py`.

Eval cleanup result:

```bash
python evals/filter_eval_by_section.py --eval-set evals/eval_set_v2_remap_v3.jsonl --corpus-jsonl ingestion/en_chunks/corpus_v3.jsonl --out evals/eval_set_v2_remap_v3_filtered.jsonl --tagged-out evals/eval_set_v2_remap_v3_tagged.jsonl --report evals/results/eval_set_v2_remap_v3_section_filter.json
```

Filtered `49/200` rows, leaving `151`. Filtered rows were overwhelmingly rice (`48/49`):
`Abstract` = `33`, `Acknowledgments` = `10`, `References` = `4`, table/results fragments = `2`.

Full eval ablation:

```bash
python evals/eval_v3_ablation.py --eval-set evals/eval_set_v2_remap_v3.jsonl --corpus-jsonl ingestion/en_chunks/corpus_v3.jsonl --model thenlper/gte-base --batch-size 64 --out evals/results/v3_ablation_full_20260531_codex.json
```

| Variant | hit@1 | hit@5 | MRR@5 | NDCG@5 | rec@20 | rec@30 |
|---|---:|---:|---:|---:|---:|---:|
| source_text | 0.090 | 0.185 | 0.126 | 0.141 | 0.330 | 0.370 |
| title_section_source | 0.075 | 0.145 | 0.102 | 0.113 | 0.280 | 0.325 |
| retrieval_text | 0.060 | 0.160 | 0.095 | 0.111 | 0.320 | 0.360 |

Filtered eval ablation:

```bash
python evals/eval_v3_ablation.py --eval-set evals/eval_set_v2_remap_v3_filtered.jsonl --corpus-jsonl ingestion/en_chunks/corpus_v3.jsonl --model thenlper/gte-base --batch-size 64 --out evals/results/v3_ablation_filtered_20260531_codex.json
```

| Variant | hit@1 | hit@5 | MRR@5 | NDCG@5 | rec@20 | rec@30 |
|---|---:|---:|---:|---:|---:|---:|
| source_text | 0.113 | 0.218 | 0.151 | 0.168 | 0.397 | 0.437 |
| title_section_source | 0.099 | 0.192 | 0.135 | 0.149 | 0.351 | 0.397 |
| retrieval_text | 0.073 | 0.199 | 0.118 | 0.138 | 0.397 | 0.444 |

Validation passed:

```bash
python -m compileall evals/eval_v3_ablation.py evals/filter_eval_by_section.py evals/audit_retrieval_v3_failures.py
python evals/filter_eval_by_section.py --help
python evals/eval_v3_ablation.py --help
python -m pytest evals/tests/test_v3_diagnostics.py
```

Verdict: filtering bad gold targets improves the measured v3 result, but the v3 corpus still
does **not** beat the current v2/prod baseline. The contextual header is not helping dense
retrieval; the best v3 representation is plain `source_text`, and even that remains below
the current 512-character v2/prod index. Do **not** proceed to Module 3 or production cutover
from this corpus. Next candidate should be conservative v2.5 work or corpus/eval relabeling,
not more retrieval plumbing on the current v3 artifact.

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
