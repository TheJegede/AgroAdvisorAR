# Spanish Translate-Bridge — Design Spec

**Date:** 2026-05-29
**Owner:** Taiwo Jegede
**Status:** Approved (design); ready for implementation plan.

## Summary

Replace the dedicated Spanish RAG (F1: bge-m3 multilingual index + ES routing)
with a **translate-bridge**: a Spanish farmer's query is translated to English,
the existing English RAG pipeline runs unchanged, and only the final user-facing
answer text is translated back to Spanish. The pipeline stays **100% English
internally** (retrieval, generation, NLI citation guard).

### Why
- The dedicated ES path was low quality (MT-bootstrap bge-m3, ~0.12 MRR) and the
  EN-only NLI citation guard scored Spanish text → over-suppression.
- The English path is now strong (gte-base index + reranker + P0/P2.1 guard
  fixes). Routing Spanish through it reuses that quality.
- Keeping the pipeline English **dissolves the Spanish-guard problem entirely** —
  no multilingual NLI needed (the planned P2.2 becomes unnecessary).
- Fits constraints: no budget, prod on Koyeb CPU (no GPU).

## Decisions (locked)

1. **Translation engine:** reuse the existing LLM provider chain (Groq primary,
   Gemini fallback). Multilingual, free-tier, runs on CPU prod (it's an API), no
   new model to host. Adds ~2 LLM calls per ES query.
2. **Boundary:** all-English internal; translate only at the edges. Query in
   (ES→EN) before classify/retrieve; answer out (EN→ES) after the guard.
3. **Trigger:** the UI `req.language == "es"` flag (reliable — user is in ES
   mode). `detect_language`/langdetect is removed.

## Data flow

```
ES query (req.language == "es")
  1. translate_to_en(message)                 # services/translation.py (LLM)
  2. classify_query(en_message)               # English, unchanged
  3. run_rag_query(en_message, language="en") # gte retrieval + EN gen + EN NLI guard, unchanged
  4. translate_advisory_to_es(advisory)       # prose fields only
  5. stream Spanish advisory to user
```
EN queries skip steps 1 & 4 (zero added overhead, identical to today).

`run_rag_query` becomes **English-only**: the `detected_lang` param and ES
vectorstore routing are deleted.

## New component: `backend/services/translation.py`

### `translate_to_en(text: str) -> str`
- One LLM call via the existing provider chain: "Translate this Arkansas
  farmer's question to English. Output only the translation."
- Failure (error/quota): log + return the original text (degraded retrieval; the
  guard catches a bad result — never blocks the query).

### `translate_advisory_to_es(advisory: AdvisoryResponse) -> AdvisoryResponse`
- **Translate (user-facing prose):** `problem_summary`, each
  `likely_causes[].cause` + `.explanation`, `recommended_actions[]`,
  `warnings[]`, `confidence_explanation`.
- **Preserve verbatim (safety/correctness):**
  - `products_rates` — product names ("Newpath") + rates ("150 lb N/acre");
    MT corrupting a rate/unit is dangerous.
  - `citations` (`document_title`) — reference real English source docs.
  - `escalation` — Extension agent name/phone/email (contact data).
  - `confidence` enum + `confidence_score` — UI localizes the badge via i18n.
- **Method:** collect prose strings into an ordered list → one LLM call returning
  a JSON array of Spanish strings → map back by index (handles list fields).
- Failure: log + return the English advisory unchanged (correct + grounded, just
  untranslated) rather than blanking.

## Removed (the dedicated ES RAG)

- `rag.py`: `_get_vectorstore_es`, `_VECTORSTORE_ES_UNAVAILABLE`, the
  `detected_lang` param + ES routing branch.
- `embedding.py`: `BGEEmbeddings`, `get_multilingual_model`.
- `config.py`: `MULTILINGUAL_EMBEDDING_MODEL_PATH`, `PINECONE_MULTILINGUAL_INDEX_NAME`.
- `ingestion/`: `translate_corpus.py`, `ingest_es_chunks.py`,
  `create_multilingual_index.py`.
- `classifier.py`: `detect_language`.
- CI: the `eval-es` job in `.github/workflows/nightly-eval.yml`.
- `backend/tests/test_f1_lang_routing.py`.
- (Optional) delete the `agroar-prod-multilingual` Pinecone index from the account.

## Kept

- Frontend i18n (`LangContext`, `frontend/src/constants/i18n.js`) — static UI
  translation, unaffected.
- `evals/ar_agqa_es.jsonl` — **repurposed** as the bridge eval: it already has
  Spanish queries + **English** gold chunks, so it directly tests
  ES query → translate → retrieve → did we hit the EN gold chunk?

## Evaluation (all free / local)

1. **Bridge retrieval:** `ar_agqa_es` → `translate_to_en` → gte retrieve →
   per-namespace recall of the EN gold chunk. Target ≈ EN `eval_set_v2` recall.
2. **End-to-end ES:** extend `answer_eval_full.py` with a bridge path (translate
   in → EN RAG → translate out), scored with the per-crop breakdown; local Qwen
   for translate+gen ($0).
3. **Translation spot-check:** eyeball ES query → EN translation → ES answer;
   confirm products/rates preserved.

## Testing (unit, mocked LLM)

- `translation.py`: prose fields translated; `products_rates`/`citations`/
  `escalation` preserved; list index-remap correct; failure → English fallback.
- `query.py`: `language=="es"` triggers translate-in/out; `"en"` skips both.

## Migration order (add-before-remove — no broken intermediate)

1. Add `services/translation.py` + unit tests (additive).
2. Wire `query.py` ES path (translate-in → EN `run_rag_query` → translate-out).
3. Make `run_rag_query` English-only — drop `detected_lang` + ES routing; update
   callers (`query.py`, `evals/answer_eval_full.py`, tests).
4. Remove ES infra (BGEEmbeddings, multilingual config, ES ingestion scripts,
   CI `eval-es`, `test_f1_lang_routing`).
5. Repurpose `ar_agqa_es` as the bridge eval + add a runner.
6. **Validate** (bridge recall + end-to-end) — only then:
7. (optional) delete `agroar-prod-multilingual` index.

## Risks

- **Query mistranslation → wrong retrieval** (main quality risk) — caught by eval #1.
- **Latency:** +2 LLM calls per ES query (acceptable for pilot).
- **Free-tier token/day budget** — ES queries cost ~2× EN; monitor.

## Out of scope (separate tracks)

- gte+reranker EN retrieval upgrade (already built: `agroar-prod-gte`).
- P2.3 per-crop NLI threshold calibration (still pending from the guard plan).
- ES translation *quality* tuning beyond "good enough for pilot".
```
