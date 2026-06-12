# Rice Failure Diagnosis — why rice correctness is stuck at 18%

> Zero-cost read of existing eval dumps (Task 1 of
> `docs/superpowers/plans/2026-06-13-rice-diagnosis-b2-format-tax.md`).
> Inputs (gitignored): `evals/_out_clean_indepjudge_b1on.jsonl` (B1-on advisory dump,
> independent Gemini judge), `evals/_retrieval_split_clean.jsonl` (retrieval split).
> Raw dump of the 19 failing items: `evals/_rice_fails.txt`.

**Context:** clean set `eval_set_v2_clean.jsonl`, DeepInfra 70B gen (B1 on = prod default),
independent Gemini 2.5-flash judge, n=40 seed=7. Rice = 19 items, corr **18%** — FLAT across
every lever (L2/L3/B1) while poultry (+13pp) and soybeans (+6pp) moved. 19/19 rice items scored
corr < 1.0; this classifies all 19.

## Bucket counts

| bucket | count | % of rice fails |
|---|---|---|
| `GOLD_ARTIFACT` (answer plausibly ok, judged vs a gold passage it didn't use — usually a yearly "br wells" research volume / TOC / citation list with no actionable content) | 8 | 42% |
| `GEN_FAILURE` (right docs in top_titles, but answer states wrong/invented numbers, products, methods or thresholds) | 8 | 42% |
| `EVAL_MISLABEL` (the query doesn't belong: wrong crop in the rice namespace, or gold pointed cross-namespace) | 3 | 16% |
| `TRUE_RETRIEVAL` (no on-topic doc in top_titles AND gold is a real dedicated doc) | 0 | 0% |

**GOLD_ARTIFACT + EVAL_MISLABEL = 11/19 = 58%** → rice 18% is *substantially an eval-measurement
problem*, not a pipeline problem. **GEN_FAILURE = 8/19 = 42%** → there is still a real generation
target (B2 is well-aimed). **TRUE_RETRIEVAL = 0** → the closed-retrieval guardrail holds; no
stop-condition fires.

## Per-item classification (bucket + reason)

| # | bucket | corr/faith | reason (≤10 words) |
|---|---|---|---|
| 1 | GEN_FAILURE | 0.5/1.0 | handbook retrieved; hallucinated incorporation timing + soil types |
| 2 | GOLD_ARTIFACT | 0.0/1.0 | gold "2023 br wells"; answered from dedicated potassium doc |
| 3 | GEN_FAILURE | 0.5/0.0 | got moisture %; hallucinated drying method (faith 0) |
| 4 | GEN_FAILURE | 0.0/0.0 | gold 2019 br wells in top5; invented crops/recs |
| 5 | GOLD_ARTIFACT | 0.0/0.5 | gold yearly volume = research context, no recommendations to use |
| 6 | EVAL_MISLABEL | 0.5/1.0 | gold pointed to SOYBEANS doc; Clearfield-rice answered from rice docs |
| 7 | GOLD_ARTIFACT | 0.0/0.5 | gold = handbook citation list; seeding-rate doc retrieved instead |
| 8 | GOLD_ARTIFACT | 0.5/0.5 | gold 2022 br wells; got night-heat core right |
| 9 | EVAL_MISLABEL | 0.0/1.0 | CORN nitrogen question sitting in rice namespace |
| 10 | EVAL_MISLABEL | 0.0/0.0 | SOYBEAN-variety question sitting in rice namespace |
| 11 | GEN_FAILURE | 0.5/0.0 | seeding-rate doc retrieved; hedged + hallucinated soil/temp factors |
| 12 | GOLD_ARTIFACT | 0.0/1.0 | gold 2020 br wells table; reasonable hedge, faith 1.0 |
| 13 | GOLD_ARTIFACT | 0.5/1.0 | gold 2022 br wells; got earlier-planting core right |
| 14 | GOLD_ARTIFACT | 0.0/1.0 | gold yearly volume; herbicide docs retrieved, faith 1.0 |
| 15 | GOLD_ARTIFACT | 0.0/1.0 | gold = TOC of a yearly volume, non-answer-bearing |
| 16 | GEN_FAILURE | 0.0/0.0 | overstated drift harm; reference says "research needed" |
| 17 | GEN_FAILURE | 0.5/1.0 | water-mgmt doc retrieved; hallucinated "intermittent flooding" |
| 18 | GEN_FAILURE | 0.0/0.0 | gold 2019 in top5; hallucinated sheath blight vs defoliation data |
| 19 | GEN_FAILURE | 0.0/0.5 | gold recommended-chemicals retrieved; invented herbicide names/rates |

## Decision

**Per the plan's Step-3 gate: GOLD_ARTIFACT + EVAL_MISLABEL ≥ 50% (58%) → rice 18% is
substantially an EVAL problem, not a pipeline problem.**

Two structural causes, both about how rice is *graded*, not how it's *answered*:

1. **Rice gold labels are pointed at the least answer-bearing docs in the corpus.** 7 of the 8
   GOLD_ARTIFACT items have gold = a yearly *"YYYY br wells arkansas rice research studies"* volume —
   research-study compilations that the judge itself describes as "merely a list of academic
   citations", "a table of contents", or "research context [that] offers no recommendations." A
   how-to query graded against a non-answer-bearing gold passage cannot score corr=1.0 no matter how
   good the answer is. Under single-gold grading, rice is penalized for its own gold quality.
2. **3 of 19 rice items are mislabels** — a corn-nitrogen question (#9) and a soybean-variety
   question (#10) sit in the rice namespace, and #6's gold points cross-namespace to a soybeans doc.

**Actions:**
- **Run B2 unchanged** (it reads on all crops, and GEN_FAILURE = 42% of rice is a genuine
  generation target). The GEN_FAILURE signature here — model hallucinates a *specific* rate / product
  / method / threshold when the retrieved doc is general — is exactly what format-tax (B2) and the
  verbatim levers (B1/L3) attack, so B2 is well-aimed.
- **Follow-up recommendation (do NOT trust any rice headline until done):** curate the rice items in
  `eval_set_v2_clean.jsonl` with the same audit procedure that produced the clean set from the
  soybean audit — (a) drop/relabel the 3 EVAL_MISLABEL items (#6, #9, #10), and (b) re-point the
  GOLD_ARTIFACT gold labels off the yearly "br wells" research volumes onto the dedicated topical
  docs the pipeline actually retrieves (potassium-requirements, seeding-rate-recommendations,
  water-management, etc.). Expect the rice headline to rise materially once gold stops pointing at
  TOCs. This is the highest-leverage rice action and it is a *data* fix, not a pipeline lever.

**No retrieval work** — TRUE_RETRIEVAL = 0/19; retrieval surfaced an on-topic doc in every failure.
The closed-retrieval guardrail is reconfirmed for rice.

---

## B2 format-tax probe — result (Task 3)

Ran n=40 seed=7, DeepInfra 70B **unconstrained** (`--two-step`: free-form gen →
`extract_json_block` parse → Groq-8b repair on failure) + independent Gemini judge, vs the
existing B1-on control (`evals/_out_clean_indepjudge_b1on.jsonl`). Only variable = the decoding
constraint (B1 on in both arms). **scored=40, skipped=0** (run survived a mid-run system sleep at
24/40: the dead socket hit its client timeout, that item retried clean, loop continued — 0 lost).
Dump: `evals/_out_clean_indepjudge_twostep.jsonl`; log: `evals/_phaseB2_run.log`.

| metric | B1-on control (B) | two-step (A) | Δ |
|---|---|---|---|
| correctness | 27.5% | **23.8%** | **−3.7pp** |
| faithfulness | 65.0% | **67.5%** | +2.5pp |
| suppression | 0% | 0% | — |

Paired (n=40): corr **helped 5 / hurt 7 / same 28**; faith helped 7 / hurt 6 / same 27.
Per-crop corr: poultry 25→38 (n=4), **rice 18→16 (n=19)**, soybeans 38→29 (n=17).

**Verdict — corr within ±5pp ⇒ FORMAT TAX DISPROVEN for this stack. B2 CLOSED.** Not only is the
delta inside the noise band, it leans **negative** (hurt > helped on corr; soybeans drop 9pp) —
i.e. for this Llama-3.3-70B + AdvisoryDraft schema, `json_mode` constrained decoding *mildly helps*
rather than taxes generation: the schema scaffolds the model. This is the **opposite** of the Tam
et al. 2024 "Let Me Speak Freely?" prior and is a publishable negative result either way. Do **not**
productionize two-step generation in `backend/services/rag.py`.

**Rice did NOT move (18→16)** under unconstrained decoding — direct confirmation of the Task 1
finding: rice 18% is an eval-measurement artifact (gold pointed at non-answer-bearing yearly
research volumes), not a generation-format ceiling. No generation lever will lift rice until the
rice gold labels are curated.

**Phase C (generation model swap) is now the live next question** — that is Taiwo's call (ongoing
prod cost); present numbers and stop, do not swap unilaterally.

## B3 (`source_quote`) redundancy decision (Task 4)

Verbatim/number-grounding rate of stated rates against retrieved chunks, from the two-step dump
(`evals/_b3_grounding.py`): **rates stated 24, grounded 11 = 46%**.

**46% < ~80% ⇒ B3 stays a LIVE candidate** (NOT closed). B1's quote-into-analysis does not yet
ground rates reliably — **54% of stated rates are not verbatim/number-grounded in the retrieved
chunks**, which is the expected headroom for an explicit `source_quote` grounding field + check.
Caveat: the metric is a crude number-substring match measured on the two-step arm; treat 54% as an
upper bound on the recoverable gap, not a precise target.
