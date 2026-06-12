# Docling v3 Index Cutover — Next Steps

`agroar-prod-gte-v3` is built (21,065 vectors, Docling-extracted, gte-base 768-dim).
HF Space env var updated to `PINECONE_INDEX_NAME=agroar-prod-gte-v3`.

---

## Option A — Validate First (Eval Gate)

**Cost:** Gemini 2.5-flash (containment judge) + DeepInfra 70B (generation). ~$0.50–$2 depending on eval set size.

Run the diagnostic eval against v3 and compare to v2 baseline:

```powershell
cd <repo root>
$env:PINECONE_INDEX_NAME="agroar-prod-gte-v3"
python -m evals.diagnostic.runner --gold evals/diagnostic/gold_labels.jsonl
```

**What to check:**
- `B-MISS` count (retrieval miss) — expect decrease vs v2 (Docling better reading order)
- `conditional_completeness_rate` — baseline 0.429; hope for lift
- `B3` (Corpus Gap) — structural, won't change from index swap alone

**Rollback:** set `PINECONE_INDEX_NAME=agroar-prod-gte-v2` in HF Space.

---

## Option B — Smoke Test (Free)

With HF Space already pointing to v3, manually test 3–5 representative queries at prod URL:

```
https://agroadvisor-eta.vercel.app
```

Test cases to cover:
- Rice: rates/timing query (table-heavy in source PDF)
- Soybeans: disease management (soybean suppression was 43% on v2)
- Poultry: general husbandry
- A dicamba/spray query (guard + citation check)
- An out-of-scope query (should still return OOS gracefully)

**Pass criteria:** answers cite real document titles, no blank/suppressed responses on known-good queries, citation guard doesn't fire spuriously.

---

## Status

- [x] Docling extractor migration (subprocess 10-page chunks, `do_table_structure=False`)
- [x] Markdown-aware chunker (MarkdownHeaderTextSplitter)
- [x] `corpus_v3.jsonl` generated (21,065 chunks, 154 docs)
- [x] `embed_corpus.py` built and run — v3 index live
- [x] HF Space env var updated
- [x] Option B: retrieval spot-check — ALL PASS (scores 0.895–0.943, 2026-06-12)
- [x] Commit ingestion changes to main (968bc42)
- [x] HF Space env var updated → LIVE in prod
- [ ] Option A: full diagnostic eval (deferred — cost; run if answer quality regressions observed)
