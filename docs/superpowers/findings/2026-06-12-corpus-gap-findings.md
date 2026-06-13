# Corpus-Gap Findings — Retrieval/Generation Split (2026-06-12)

## Method
Zero-LLM-cost. `evals/retrieval_precision.py` reproduced the seed=7 n=20 sample,
ran retrieval-only top-5 on `agroar-prod-gte-v3` (local gte-base embed + Pinecone),
joined gold-document hit@5 against the correctness/faithfulness already scored in
`evals/_out_v3_L2on.jsonl` (L2-on) and `evals/_out_v3_L2off.jsonl` (baseline).
Labels: RETRIEVAL_MISS (gold doc not retrieved) / GEN_SPECIFICITY (gold doc
retrieved, grounded, wrong specifics) / GEN_HALLUCINATION (gold doc retrieved,
ungrounded) / OK (corr >= 0.5).

### IMPORTANT deviation — chunk_id hit@5 was impossible; used document-level hit@5
The plan assumed an exact gold-`chunk_id` hit@5. That is **structurally invalid on
v3**: the Docling v3 re-ingest (968bc42, same day) re-chunked every document, so
chunk_ids changed and **zero** eval-set gold chunk_ids exist in `agroar-prod-gte-v3`
(verified via `index.fetch` — all gold ids present in v2, none in v3). An exact
chunk_id hit@5 against v3 is therefore always-miss garbage (it produced a bogus
"100% RETRIEVAL_MISS"). The dump's corr/faith were generated on v3 (per the L2
paired-eval), so the join must be against v3.

`document_title` survived the migration as a stable exact key (same vocabulary in
both indexes), so the diagnostic asks the joinable question: **did v3 top-5 surface
the gold SOURCE DOCUMENT?** Coarser than passage-level but exact, threshold-free,
and aligned to the index that produced the scored answers. (Dense cosine-to-gold
was also tried and rejected: same-crop agronomy text floors at ~0.83 cosine, so it
cannot discriminate the gold passage from same-topic text — see calibration in the
session log. "hit5" below = gold document in top-5.)

Local `.env` still points `PINECONE_INDEX_NAME` at the stale `agroar-prod-gte-v2`;
the runner now defaults `--index agroar-prod-gte-v3` so re-runs are correct
regardless of the stale env.

## Taxonomy (L2-on)
```
=== FAILURE TAXONOMY (all crops) ===
  OK                 10
  RETRIEVAL_MISS     3
  GEN_SPECIFICITY    6
  GEN_HALLUCINATION  1
```

## Per-crop (L2-on)
```
  poultry   OK=2  RETRIEVAL_MISS=1  GEN_SPECIFICITY=1  GEN_HALLUCINATION=0
  rice      OK=6  RETRIEVAL_MISS=2  GEN_SPECIFICITY=0  GEN_HALLUCINATION=1
  soybeans  OK=2  RETRIEVAL_MISS=0  GEN_SPECIFICITY=5  GEN_HALLUCINATION=0
```

## Taxonomy + per-crop (L2-off baseline)
```
=== FAILURE TAXONOMY (all crops) ===
  OK                 5
  RETRIEVAL_MISS     4
  GEN_SPECIFICITY    10
  GEN_HALLUCINATION  1

  poultry   OK=2  RETRIEVAL_MISS=1  GEN_SPECIFICITY=1  GEN_HALLUCINATION=0
  rice      OK=2  RETRIEVAL_MISS=3  GEN_SPECIFICITY=3  GEN_HALLUCINATION=1
  soybeans  OK=1  RETRIEVAL_MISS=0  GEN_SPECIFICITY=6  GEN_HALLUCINATION=0
```

## Read
- **Dominant failure label = GEN_SPECIFICITY (6 of 10 failures L2-on; 10 of 15 L2-off).**
  Therefore the next lever is **generation (L3 "quote the exact rate/product from the
  cited chunk")**, NOT corpus coverage. The prior "corpus-coverage gap" hypothesis
  (from the L1/L2 memory) is **contradicted** by this split.
- **RETRIEVAL_MISS = 3 (L2-on) / 4 (L2-off)** — only ~1/3 of failures are
  retrieval/corpus (gold document absent from top-5). All 3 L2-on misses are rice/
  poultry, none soybean.
- **GEN_SPECIFICITY = 6** — right document in hand, wrong number/product. L2 few-shot
  exemplars already converted 4 of these to OK (GEN_SPECIFICITY 10→6, OK 5→10),
  confirming this bucket is generation-fixable with no corpus work. An L3 directive
  ("cite and quote the exact rate/product from the retrieved chunk") targets the
  remaining 6 directly.
- **Soybeans specifically: 0 RETRIEVAL_MISS, 5 GEN_SPECIFICITY.** The soybean "14%
  correctness" is NOT a retrieval/corpus problem — the right documents are retrieved
  every time. It is a generation-specificity problem **compounded by eval-label
  noise** (see audit below): all 5 soybean failures hit the same gold doc
  "soybeans recommended chemicals for weed and brush control", and several queries are
  off-domain for that label.
- **GEN_HALLUCINATION = 1** (a rice item) — negligible; guard/suppression confirmed
  0% elsewhere, so guard work stays closed.

## Items flagged for label audit (Task 4)
Soybean-bucket failures whose query topic does not match a soybean weed/brush label:
- `"I'm growin' Clearfield rice, can I use Beyond Xtra..."` — **Clearfield RICE**, tagged soybeans.
- `"I got a bunch of new pine seedlings..."` — **pine seedlings / forestry**, out of rice/soy/poultry scope.
- `"How much chemical should I put in my sprayer to cover 40 acres..."` — generic **spray-math**, no crop.
- `"I got a field with them pesky horseweeds and wild garlic..."` / `"...broadleaf weeds and brush..."` — generic weed/brush, plausibly KEEP as soybean weed control.

## Eval-set label audit (Task 4)
Decided from query text + gold `document_title` only; original `eval_set_v2.jsonl`
NEVER mutated → cleaned copy `evals/eval_set_v2_clean.jsonl`.

| Query (substring) | namespace | gold doc | decision | reason |
|---|---|---|---|---|
| "Clearfield rice" / Beyond Xtra | soybeans | soybeans recommended chemicals... | **RELABEL rice** | Clearfield + Beyond Xtra is a RICE herbicide-tolerance question, mis-tagged soybeans |
| "pine seedlings" | soybeans | soybeans recommended chemicals... | **DROP** | forestry — out of rice/soy/poultry advisory scope |
| "cover 40 acres" (sprayer math) | soybeans | soybeans recommended chemicals... | **DROP** | generic application-rate/calibration math, no crop anchor; gold doc is not the answer source |
| "horseweeds and wild garlic" | soybeans | soybeans recommended chemicals... | KEEP | real soybean burndown targets (marestail + wild garlic) |
| "broadleaf weeds and brush" | soybeans | soybeans recommended chemicals... | KEEP | soybean weed/brush control |
| "low yields on my soybeans, what fertilizer" | soybeans | soybeans ch 5 fertilization | KEEP | correct |
| "fixin' to plant soybeans, seeds per acre" | soybeans | soybeans ch 7 planting | KEEP | correct |

Borderline (KEEP, noted not acted): rice "...nitrogen... to get a good corn" mentions
*corn* but is tagged rice — likely transcription noise; rice N is in-scope, left as-is
to stay conservative/reproducible.

Net change vs original: 1 RELABEL (soybeans→rice), 2 DROP. Of the 5 soybean failing
items, 3 are mislabel/out-of-scope, leaving 2 genuine soybean weed-control items — so
the soybean "14%" is measured on a bucket that is ~60% contaminated at the sampled n.
