# Batched DeepInfra Eval — plan (2026-06-12)

Goal: in one sitting, measure (1) Docling **v3 corpus lift**, (2) **L2 few-shot
exemplar** effect, and (3) run the **F5 contamination probe** — using the same
harness + config as the 2026-06-05 baseline so numbers are comparable.

## What we're comparing against (on record)
- **v2 baseline (2026-06-05):** DeepInfra 70B gen+judge, `agroar-prod-gte-v2`,
  n=20 seed=7 → **correctness 20%, faithfulness 40%, suppression 15%**.
  (No L2; L1 not yet built. L1 later measured a NO-OP, so baseline ≈ "no levers".)

## Known caveats (accept, don't re-litigate)
1. **Judge-on-self bias.** `--provider deepinfra` uses the *same* 70B for
   generation AND judging → scores are optimistic. The v2 baseline has the
   identical bias, so **deltas between our runs are valid**; absolute numbers are
   not ground truth. (The harness prints this warning itself.)
2. **n=20 is noisy.** Treat <~5pp moves as noise, same as the L2-guard-merge
   read (27.5% vs 30% "within noise"). We're looking for a real lift, not a
   decimal.
3. Local `.env` currently pins `PINECONE_INDEX_NAME=agroar-prod-gte-v2` — we
   override to v3 inline per-run; **do not edit `.env`** (prod HF already runs
   v3; root `.env` is the dev/eval default and we leave it).

## Pre-req: capture citations for the F5 probe (small tooling add)
`answer_eval_full.py` prints scores + rationales but **not** the advisory
citations, which is what the F5 probe needs. Add a `--dump <path>` flag that
writes one JSON line per scored item including `adv.get("citations")` and the
query/namespace. No production code touched; eval-only; no test needed.

Then the probe is a grep over the dump for the exemplar's fake citation strings:
`"Arkansas Herbicide Guide 2026"`, `"Arkansas Insect Management Handbook 2026"`,
`county_fips 05031` appearing **as a citation the model emitted** (note: 05031 is
also the eval county, so match on the *title* strings primarily; treat a fips-only
hit as weak signal).

## Cost (corrected from the DeepInfra dashboard)
DeepInfra Llama-3.3-70B-Turbo billed **$0.27 for ALL of last month** (1.94M
tokens / 1.57K requests — every eval run combined). One n=20 run ≈ **$0.01–0.02**.
The earlier ~$1/run estimate was ~20–50× too high. Cost is no longer a gate;
A+B together is ~pennies.

## Runs (3 total; C optional)
All from repo root, `seed=7`, `sample=20`, DeepInfra provider.

**Run A — v3 + L2 ON (current `main` = candidate prod config):**
```bash
PINECONE_INDEX_NAME=agroar-prod-gte-v3 EMBEDDING_MODEL_PATH=thenlper/gte-base \
python evals/answer_eval_full.py --provider deepinfra --sample 20 --seed 7 \
  --dump evals/_out_v3_L2on.jsonl | tee evals/_log_v3_L2on.txt
```

**Run B — v3 + L2 OFF (isolates L2 by holding corpus = v3 constant):**
Toggle the exemplars off by checking out the prompt at the pre-L2 commit
(`e583587^` has L1's CONDITIONAL_RULE_BLOCK but not the L2 exemplars), run, then
restore:
```bash
git checkout e583587^ -- backend/utils/prompt.py
PINECONE_INDEX_NAME=agroar-prod-gte-v3 EMBEDDING_MODEL_PATH=thenlper/gte-base \
python evals/answer_eval_full.py --provider deepinfra --sample 20 --seed 7 \
  --dump evals/_out_v3_L2off.jsonl | tee evals/_log_v3_L2off.txt
git checkout HEAD -- backend/utils/prompt.py   # restore L2
```

**Run C (OPTIONAL) — ES bridge parity** (only if you want a fresh ES number):
```bash
PINECONE_INDEX_NAME=agroar-prod-gte-v3 EMBEDDING_MODEL_PATH=thenlper/gte-base \
python evals/answer_eval_full.py --provider deepinfra --sample 20 --seed 7 \
  --bridge --eval-set evals/ar_agqa_es.jsonl --dump evals/_out_v3_es.jsonl
```

## How we read the result
| Delta | Computed as | Meaning |
|---|---|---|
| **v3 corpus lift** | Run B − v2 baseline (20/40) | Did Docling v3 retrieval raise answer quality? (L1 no-op, so B ≈ corpus-only) |
| **L2 exemplar effect** | Run A − Run B | Do worked multi-branch examples improve correctness/faithfulness? |
| **F5 bleed** | grep dumps for exemplar titles | Any → F5 confirmed; rename citations to `EXAMPLE-DOC-A` + gate exemplars off follow-ups. None → close F5 as no-op. |

Per-namespace table prints automatically (watch soybeans suppression + rice
correctness, the two weak spots from baseline).

## Decisions for you (Taiwo) before I run
1. **2 runs (A+B, ~$2) or 1 run (A only, ~$1)?** A-only conflates corpus+L2 but
   answers "is current prod config better than baseline." A+B cleanly separates
   them. **Recommend A+B** — without B we can't attribute the move.
2. **Include the optional ES run C (+~$1)?** Recommend **skip** for now; ES is a
   translate-bridge over the same English pipeline, low marginal info this round.
3. OK to add the `--dump` flag to `answer_eval_full.py`?

## After the eval (depends on numbers)
- Update PROGRESS.md "RESUME HERE" + the v3 config table + memory with the new
  numbers; close or action F5 per the probe.
- If v3 lift is real → that's the headline for the arXiv honest-number draft.
- If both flat → next lever is corpus-coverage gap analysis (soybeans/rice
  specifics), per PROGRESS #3.
