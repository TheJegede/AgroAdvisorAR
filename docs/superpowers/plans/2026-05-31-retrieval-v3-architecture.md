# Retrieval v3 Architecture Plan

**Status 2026-05-31:** STOPPED as a production path after Modules 0-2. Do not continue
Modules 3-7 on the current v3 corpus.

**Outcome:** Module 0 produced useful reusable eval infrastructure, and Modules 1-2 produced
a deterministic metadata-rich v3 corpus/index, but the candidate failed its early retrieval
gate. The valid v3 index (`agroar-prod-retrieval-v3-gte`) scored `hit@5=0.160` on the full
remapped eval, below current v2/prod `~0.245-0.250`. A failure audit showed many brittle
single-gold targets (`Abstract`, `Acknowledgments`, `References`, table fragments), but
filtering 49/200 weak targets still left the best v3 ablation (`source_text`) at only
`hit@5=0.218`. The contextual header variant (`retrieval_text`) was worse than plain
`source_text`, so the contextual chunk-text bet did not pay off for dense retrieval.

**Practical decision:** keep the harness/audit tools from this plan, but return production
thinking to the known-good v2/prod retrieval shape: 512-character source-text chunks,
gte-base embeddings, dense top-5, reranker off. Next work should be conservative v2.5
metadata/display improvements, corpus-coverage/eval relabeling, and prod-like 70B answer
eval when Groq quota/paid tier allows.

**Useful artifacts to keep:**
- `evals/eval_retrieval_matrix.py`
- `evals/audit_retrieval_v3_failures.py`
- `evals/filter_eval_by_section.py`
- `evals/eval_v3_ablation.py`
- `evals/tests/test_eval_retrieval_matrix.py`
- `evals/tests/test_v3_diagnostics.py`

**Do not ship from this plan:** backend hybrid retrieval, hybrid reranking, Small2Big, intent
routing, or production cutover based on the current v3 corpus/index.

**Goal:** replace the current dense-only, fixed-character chunk retrieval path with a
measured, metadata-rich, hybrid retrieval system that improves answer correctness without
lowering faithfulness.

**Current baseline to beat:**
- Dense gte retrieval on the current eval: `hit@5=0.25`, `MRR@5=0.1456`.
- Query expansion spike: raw `hit@5=0.275`, rewrite `0.280`, HyDE `0.180`.
- Local answer eval baseline: `40.0%` correctness, `82.5%` faithfulness, `5%`
  suppression.
- Current confidence signal remains weak; recent eval output showed
  `answer_confidence_mean=0.1537`.

**Non-negotiable gates before production cutover:**
- `hit@5 >= 0.40` on the current 200-item retrieval eval.
- `candidate_recall@30 >= 0.65` before reranking.
- answer correctness improves from `40%` to at least `55%` on the same sampled
  answer eval protocol.
- faithfulness stays `>= 80%`.
- suppression rate stays `<= 15%` unless deliberately changed by policy.
- p95 retrieval + rerank latency is acceptable for the target backend tier.

**Important constraint:** no retrieval change ships because it is fashionable. Every module
below must produce eval evidence before it becomes the production default.

---

## Module 0 — Evaluation Harness First

**Purpose:** make every retrieval experiment comparable and prevent another ambiguous
"better retrieval" claim.

**Tasks:**
- Add a single eval command or script that runs dense-only, sparse-only, hybrid, and
  hybrid+rerank against the same eval set and prints one table.
- Track `hit@1`, `hit@5`, `MRR@5`, `NDCG@5`, `candidate_recall@20`,
  `candidate_recall@30`, and per-namespace breakdown.
- Extend answer eval reporting with correctness, faithfulness, confidence mean,
  suppression rate, and per-namespace/per-intent breakdown.
- Store each run under `evals/results/` with index name, embedding model, chunking version,
  reranker model, and env flags.

**Files likely touched:**
- `evals/eval_runner.py`
- `evals/eval_hybrid.py`
- `evals/answer_eval_full.py`
- new `evals/eval_retrieval_matrix.py` if keeping the current scripts separate is cleaner.

**Acceptance gate:**
- One command produces a comparable baseline table for current prod, v2 title index, and
  any v3 candidate index.

**Comments:**
- This comes before ingestion work because otherwise we will not know whether v3 helped.
- Keep the old single-gold metrics, but do not rely on them alone. They are useful for
  regressions, not perfect truth.

---

## Module 1 — Section-Aware Corpus Extraction

**Purpose:** replace fixed 512-character chunking with a document model that preserves
title, year, page, section, subsection, table context, and crop metadata.

**Tasks:**
- Build a normalized document record:
  - `doc_id`
  - `document_title`
  - `source_url`
  - `crop_type`
  - `pub_year`
  - `doc_type`
  - `page_start`
  - `page_end`
  - `section_heading`
  - `subsection_heading`
  - `chunk_id`
  - `parent_section_id`
- Extract page numbers and headings from PDFs where possible.
- Convert useful tables into markdown or row-level text with captions.
- Preserve source text separately from retrieval text.
- Produce a corpus artifact such as `ingestion/en_chunks/corpus_v3.jsonl`.

**Files likely touched:**
- `ingestion/extractor.py`
- `ingestion/chunker.py`
- `ingestion/pipeline.py`
- `ingestion/ingest_en_gte.py` or a new `ingestion/ingest_retrieval_v3.py`
- `ingestion/tests/`

**Acceptance gate:**
- At least 95% of chunks have non-empty `document_title`.
- At least 70% of long-form handbook/guide chunks have non-empty `section_heading` or
  `parent_section_id`.
- Corpus generation is deterministic: same input PDFs produce stable `chunk_id`s.

**Comments:**
- This is the highest-leverage module. Better reranking cannot recover evidence that was
  split away from its heading, page, table, or exception text.
- Do not overwrite the live `agroar-prod-gte` index. Build a new v3 index.

---

## Module 2 — Contextual Chunk Text

**Purpose:** improve retrievability by embedding/indexing chunks with enough local document
context to disambiguate them.

**Tasks:**
- Generate a short retrieval header for each chunk, for example:
  `Arkansas Rice Management Guide 2026 | Soil Fertility | preflood nitrogen timing and
  soil texture caveats.`
- Prepend the header to text used for dense embeddings and sparse indexing.
- Keep original chunk text unchanged for citations and display.
- Store both fields:
  - `retrieval_text`
  - `source_text`

**Files likely touched:**
- `ingestion/chunker.py`
- `ingestion/ingest_retrieval_v3.py`
- `backend/services/rag.py` only after cutover, if source/display behavior changes.

**Acceptance gate:**
- Dense retrieval on v3 contextual chunks beats current `hit@5=0.25`.
- No citation display regression: returned snippets still show original Extension text,
  not only synthetic headers.

**Comments:**
- This follows the contextual retrieval pattern: add concise chunk-specific context before
  embedding/BM25, but cite the original source.
- Start with deterministic metadata headers before using an LLM to generate summaries.

---

## Module 3 — Hybrid Candidate Retrieval

**Purpose:** recover exact product names, rates, pests, slang, and technical terms that dense
embeddings miss.

**Tasks:**
- Add sparse retrieval over the same v3 chunk IDs.
- Start with BM25 because the repo already has `evals/hybrid_core.py`.
- Retrieve:
  - dense top 30
  - sparse top 30
  - optional metadata-filtered top N for high-risk intents.
- Fuse candidate lists with reciprocal rank fusion.
- Deduplicate by `chunk_id`.
- Preserve candidate source: dense, sparse, or both, for diagnostics.

**Files likely touched:**
- `evals/hybrid_core.py`
- new `backend/services/retriever.py`
- `backend/services/rag.py`
- possibly a serialized local BM25 artifact under `ingestion/` or a hosted search backend.

**Acceptance gate:**
- `candidate_recall@30 >= 0.65`.
- Hybrid candidates beat dense-only candidate recall by at least 10 absolute points.
- Latency is measured on the intended backend host.

**Comments:**
- Do not compare BM25 and cosine raw scores directly. Use RRF or explicit normalization.
- If BM25 is flat again, inspect by intent before rejecting sparse retrieval globally.
  Sparse often helps product/rate/safety queries more than general semantic queries.

---

## Module 4 — Cross-Encoder Reranking

**Purpose:** turn a broad, noisy candidate pool into a small high-precision context set.

**Tasks:**
- Rerank hybrid candidates, not just dense candidates.
- Start with the configured `BAAI/bge-reranker-v2-m3`.
- Rerank top 40 candidates to final top 5-8.
- Record reranker score in retrieved chunk diagnostics.
- Keep dense-only fallback if the reranker is unavailable.

**Files likely touched:**
- `backend/services/reranker.py`
- new `backend/services/retriever.py`
- `backend/config.py`
- `evals/eval_retrieval_matrix.py`

**Acceptance gate:**
- `hit@5 >= 0.40`.
- `MRR@5` improves over dense-only v3.
- p95 rerank latency is acceptable for the chosen host.

**Comments:**
- The current `RERANK_ENABLED` path exists but is not enough because it reranks dense
  candidates only.
- If CPU latency is too high, keep reranking for eval and paid/GPU deployment while
  production free tier uses the best non-reranked hybrid path.

---

## Module 5 — Small2Big Context Assembly

**Purpose:** retrieve precise child chunks but generate from enough parent section context to
answer correctly.

**Tasks:**
- Store parent section text for each child chunk.
- After reranking child chunks, expand final chunks to:
  - parent section, or
  - neighboring chunks within the same section, capped by token budget.
- Deduplicate overlapping parent contexts.
- Keep citations anchored to child chunks with title/page/section.
- Add prompt formatting that clearly separates retrieved evidence blocks.

**Files likely touched:**
- new `backend/services/retriever.py`
- `backend/utils/prompt.py`
- `backend/services/rag.py`
- `models/advisory.py` only if citation schema needs page/section expansion.

**Acceptance gate:**
- Answer correctness improves without faithfulness dropping below `80%`.
- The prompt context does not exceed the configured model budget.
- At least one eval run shows fewer incomplete-but-faithful answers.

**Comments:**
- This addresses the observed failure mode where answers are grounded but incomplete.
- The final LLM should see enough section context to include rates, exceptions, and
  adjacent warnings.

---

## Module 6 — Intent-Aware Routing

**Purpose:** route by farmer task, not only crop namespace.

**Tasks:**
- Add intent labels:
  - pest/disease diagnosis
  - herbicide/pesticide/rate
  - irrigation/AWD
  - fertility/soil test
  - variety/planting
  - poultry housing/water/feed/lighting
  - market/economics
  - safety/regulatory
- Add deterministic keyword hints for high-risk intents before falling back to LLM routing.
- Use intent to tune retrieval:
  - metadata filters
  - document-type boosts
  - sparse weighting
  - final context size
  - safety document inclusion.

**Files likely touched:**
- `backend/services/classifier.py`
- new `backend/services/retriever.py`
- `backend/services/rag.py`
- `backend/tests/test_rag_retrieval.py`
- new classifier/retriever tests.

**Acceptance gate:**
- Per-intent eval output exists.
- Safety/regulatory and pesticide/rate queries reliably include safety/label guidance where
  available.
- Intent routing does not regress crop namespace routing.

**Comments:**
- Crop-only routing is too coarse for agricultural advice. A rice nitrogen question and a
  rice disease question should not retrieve with identical settings.

---

## Module 7 — Production Cutover And Rollback

**Purpose:** ship only after v3 proves better than the current system, with a clean rollback.

**Tasks:**
- Build `agroar-prod-retrieval-v3` or similarly named index.
- Run retrieval matrix eval.
- Run answer eval on the same seed/sample as the baseline.
- Smoke test English and Spanish translate-bridge queries.
- Flip backend env only after gates pass:
  - `PINECONE_INDEX_NAME=<v3 index>`
  - matching `EMBEDDING_MODEL_PATH`
  - retrieval feature flags.
- Keep old index available for rollback.

**Acceptance gate:**
- All non-negotiable gates at the top of this plan pass.
- Browser smoke test shows real citations and non-empty grounded answers.
- Rollback is one env change back to the previous index/config.

**Comments:**
- Do not cut over just because retrieval metrics improve if answer eval regresses.
- Do not delete `agroar-prod-gte` or `agroar-prod-gte-v2` until v3 has been stable in
  production.

---

## Deprioritized Approaches

**HyDE:** deprioritized because the local spike showed regression: raw `hit@5=0.275`,
HyDE `hit@5=0.180`.

**Generic query rewrite:** deprioritized because the local spike was flat: raw `0.275`,
rewrite `0.280`.

**Embedding fine-tuning:** defer until v3 corpus and eval labels are clean. Fine-tuning on
noisy chunk IDs can optimize the wrong target.

**Prompt-only work:** not enough. Current failures point to evidence coverage and candidate
quality, not only output formatting.

---

## Suggested Implementation Order

1. Module 0 — Evaluation harness first.
2. Module 1 — Section-aware corpus extraction.
3. Module 2 — Contextual chunk text.
4. Module 3 — Hybrid candidate retrieval.
5. Module 4 — Cross-encoder reranking.
6. Module 5 — Small2Big context assembly.
7. Module 6 — Intent-aware routing.
8. Module 7 — Production cutover and rollback.

Each module should land as a small PR or commit series with its own test/eval output. The
plan is successful only if the final system improves answer correctness while preserving
faithfulness and citation quality.
