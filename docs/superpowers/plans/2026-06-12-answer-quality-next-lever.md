# Answer-Quality Next Lever — Measure-First Plan

> **Status: PROPOSED (awaiting Taiwo's go on the cost-gated Phase A run).**
> **Goal:** push the honest answer-quality headline above today's **35% correctness /
> 52% faithfulness** — but choose the lever on a *trustworthy* baseline, not the current
> noisy/contaminated/self-judged 35%.

---

## Why not just build a lever now (read first)

Today's 35% corr / 52% faith is a **bad number to steer by** — three defects stacked:

1. **Contaminated eval bucket.** 3 of 5 soybean failures are KNOWN mislabels (a Clearfield-
   *rice* question tagged soybeans, a pine-seedling forestry question, generic sprayer-coverage
   math). The cleaned set `evals/eval_set_v2_clean.jsonl` (198 items: 1 relabel soybeans→rice,
   2 drops) was **built** in the corpus-gap split but the headline was **never re-measured on it**.
2. **Self-judge bias.** All paired runs use DeepInfra 70B for BOTH generation AND judging →
   optimistic absolute scores (paired Δ valid, absolute not ground truth — the harness warns this itself).
3. **n=20 noise.** Treat <~5pp moves as noise (same rule as the L2-guard-merge read).

Net: the *true* number could already be **higher** than 35% (we're penalizing label noise) OR
the 35% could be **inflated** by self-grading. Building a generation lever now risks chasing an
artifact. **Measure the real baseline first — it's near-free and it's the prerequisite for
picking the right build lever.**

## What is OFF the table (do NOT re-propose — already disproven)

- **Retrieval techniques** — 5 levers tested + rejected (token-chunking, hybrid BM25, query
  rewrite, HyDE, ms-marco reranker). Corpus-gap split confirmed retrieval surfaces the right
  *document* in ~2/3+ of failures; **soybeans had 0 RETRIEVAL_MISS**. Retrieval is not the gap.
- **Guard / over-suppression** — **0% suppression** across all crops in every recent dump.
  Root cause solved (LLM-as-judge). Closed. Do not reopen.
- **Corpus coverage / re-ingest as the soybean lever** — the split CONTRADICTED this; gap is
  GEN-SPECIFICITY not missing corpus.

---

## Phase A — Trustworthy baseline (DO FIRST · cost-gated ~$0.05–0.10)

**Purpose:** replace the noisy/contaminated/self-judged 35% with a number we can build on
(and publish in NIW/arXiv). Three changes vs the current measurement, all at once:

- **A1. Clean eval set.** Run on `evals/eval_set_v2_clean.jsonl` (not `eval_set_v2.jsonl`) so
  mislabeled items can't force-penalize correctness. (Recall: `answer_eval_full.py` force-
  retrieves into the gold `namespace` — a mislabeled item *cannot* score correct.)
- **A2. Independent judge.** Judge with **Gemini 2.5-flash** (the existing containment-judge
  model, `CONTAINMENT_JUDGE_MODEL`), NOT the 70B generator → removes self-grading bias.
  Generation stays DeepInfra 70B (matches prod + prior baselines for comparability).
- **A3. Bigger n.** Bump n=20 → **n≈40** (seed=7) so a real lift is distinguishable from noise.

**Run (cost-gated — get OK before executing):**
```bash
# from repo root; .env lives here
PINECONE_INDEX_NAME=agroar-prod-gte-v3 \
python evals/answer_eval_full.py --provider deepinfra \
  --eval-set evals/eval_set_v2_clean.jsonl \
  --sample 40 --seed 7 \
  --judge-provider gemini \
  --dump evals/_out_clean_indepjudge.jsonl
```
> Verify the `--judge-provider` / clean-set / sample flags exist in `answer_eval_full.py` before
> running; wire the minimal flag if missing (eval-only, no prod code, no test needed) — same
> pattern as the earlier `--dump` add.

**Outputs:** corr / faith / suppression overall + per-crop, on a clean set, independently judged,
n≈40. Plus the per-item dump for the split re-classification.

**Decision gate (drives Phase B vs C):**
- Re-run the zero-cost `evals/retrieval_precision.py` split on the new dump → fresh taxonomy
  counts (RETRIEVAL_MISS / GEN_SPECIFICITY / GEN_HALLUCINATION / OK).
- **If GEN_SPECIFICITY + GEN_HALLUCINATION still dominate** → do **Phase B**.
- **If failures are flat across all categories** (no single dominant cause) → 70B is the ceiling
  → do **Phase C**.
- **If the clean+independent number is already materially higher** (e.g. corr ≥ ~50%) → re-baseline,
  re-decide whether any further lever clears the cost/risk bar at all.

---

## Phase B — L3 Stage-2: verifiable verbatim grounding (BUILD · conditional on A)

The parked Stage-2 of the L3 lever. Makes rate/product specificity **verifiable**, not just
encouraged — attacks the residual GEN_SPECIFICITY (4) + GEN_HALLUCINATION (1) AND structurally
lifts faithfulness (the more safety-critical number).

- **B1.** Add optional `source_quote` (verbatim rate/product string) to each `Product` in
  `backend/models/advisory.py`.
- **B2.** Zero-cost grounding check in `backend/services/rag.py` post-process: the `source_quote`
  string must appear in a retrieved chunk; if absent → downgrade confidence / flag (do NOT blank —
  guard over-suppression stays closed).
- **B3.** TDD: unit tests for the grounding check (present/absent/whitespace-drift cases).
- **B4.** Measure one paired A/B on the Phase-A harness (clean set, independent judge).

**Risk to respect:** `advisory.py:35-44` documents that exposing extra LLM-filled schema fields
previously made the model hallucinate / crash structured output / drop advisories. So `source_quote`
is **optional** + grounding is a post-process check, not a new required field. If structured-output
breakage reappears → fall back to a directive-only variant (prompt, no schema change).

---

## Phase C — Generator model swap (TEST · conditional on A, cost-aware)

Only if Phase A shows a flat ceiling (70B states wrong numbers from right chunks across the board
= reasoning/extraction limit, not a fixable prompt/grounding gap).

- **C1.** Pick a stronger candidate via the `claude-api` skill (current model IDs/pricing) and/or a
  larger DeepInfra/Groq open model. Consult skill — do not pick from memory.
- **C2.** Run the **Phase-A harness unchanged** with only the generator swapped → directly comparable
  corr/faith delta.
- **C3.** Weigh lift vs ongoing per-query cost (user is cost-averse; prod is currently free-tier
  Groq-primary). A model swap changes the prod cost profile — decision is Taiwo's, with numbers in hand.

---

## Cost ledger (state + OK before any paid run — durable guardrail #4)

| Phase | Paid? | Est. |
|---|---|---|
| A (clean + independent judge + n40) | yes | **$0.05–0.10** |
| B build + unit tests | no | $0 |
| B measure (paired) | yes | ~$0.02–0.04 |
| C test run | yes | ~$0.05 (+ ongoing if adopted) |

Reference: whole last month of DeepInfra evals = **$0.27**. Cost is small but per the rule each
paid run is OK-gated.

---

## Recommendation

**Run Phase A now.** It's near-free, de-noises the headline, gives the NIW/arXiv-publishable number,
and is the prerequisite for choosing B vs C rationally. Then let the decision gate pick the build lever.
Do NOT build B or C before A — risks fixing an artifact.

## Open question for Taiwo

- Approve the **~$0.05–0.10 Phase A run**? (yes → I run it and report the clean/independent baseline +
  the fresh split, then we pick B or C together.)
