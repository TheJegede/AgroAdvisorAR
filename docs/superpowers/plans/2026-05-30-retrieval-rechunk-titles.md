# Title-Metadata Cutover (only remaining task)

**Status 2026-05-31:** the v2 index is BUILT and retrieval-verified. The only task left is
the **gated prod cutover**, which is blocked on Groq TPD (needs an answer-eval).

**What is already done (do not redo):**
- `agroar-prod-gte-v2` built clean — 512-char chunks + `document_title` metadata, 20,546
  vectors (rice 16126 / soybeans 4077 / poultry 343).
- Retrieval eval (n=200, dense, no rerank): **hit@5 0.25 = baseline, no regression** — as
  expected (titles aren't embedded; the win is the citation guard validating real titles
  → un-floors "Low" confidence, which only shows at answer-eval).
- `evals/eval_set_v2_remap.jsonl` regenerated against the current char corpus.

---

## Remaining: Step 4 — Gated prod cutover

**Gate:** do NOT cut over until an answer-eval on v2 confirms confidence un-floors off "Low".
That needs LLM generation → **blocked until Groq TPD resets or a paid Dev tier**. (Retrieval
being flat is not enough on its own — the whole point of titles is the guard/confidence path.)

**When Groq generation is available again:**

1. **Answer-eval A/B** (free local-Qwen is fine for relative signal; prod Groq-70b is the real
   confirmation): compare old `agroar-prod-gte` vs `agroar-prod-gte-v2`.
   ```bash
   python evals/answer_eval_full.py --provider local --sample 20   # baseline (old index)
   PINECONE_INDEX_NAME=agroar-prod-gte-v2 python evals/answer_eval_full.py --provider local --sample 20
   ```
   Confirm: confidence no longer floored to Low on grounded answers; correctness/faithfulness
   not regressed vs the 40% / 82.5% baseline.

2. **Flip prod env** (only if Step 1 is positive): set HF Space
   `PINECONE_INDEX_NAME=agroar-prod-gte-v2` (keep `EMBEDDING_MODEL_PATH=thenlper/gte-base`).

3. **Browser smoke test** EN + ES — one grounded query each; confirm a real citation renders
   and confidence is not floored.

4. **Rollback path:** revert HF env to `agroar-prod-gte`. Leave the old index in place until
   v2 is proven in prod.

---

## Known limitation

`section_heading` stays `""` — the chunker/pipeline never extracts real section headings.
This work delivers `document_title` (what the guard checks); real heading extraction is a
separate future task, intentionally out of scope.
