# Answer-Quality Next Lever — Measure-First Plan

> **Status: EXECUTED 2026-06-12 — Phase A done, gate picked B1, B1 BUILT (TDD, 9 tests,
> backend 300 green) + MEASURED WIN (paired n=40: corr 23.8%→27.5% helped 7/hurt 3,
> faith 57.5%→65.0% helped 10/hurt 6, 0 skips) + SHIPPED default-ON. Remaining: B2 probe
> (optional, also settles Phase C), B3 likely redundant. PHASE A RESULTS:** Honest baseline (clean 198-set,
> DeepInfra 70B gen, independent Gemini 2.5-flash judge, n=40 seed=7, 0 skipped):
> **corr 23.8% / faith 57.5% / supp 0%** (poultry 12% n=4, rice 18% n=19, soybeans 32% n=17 —
> crop ranking FLIPPED vs contaminated set; soybeans was never the weak crop, its labels were).
> Self-judge inflation confirmed ≈ +11pp corr (35%→23.8%). Split: OK 15 / RETRIEVAL_MISS 12 /
> GEN_SPECIFICITY 8 / GEN_HALLUCINATION 5 — but item audit shows RETRIEVAL_MISS ≈ 85% artifact
> (5 near-duplicate yearly-series docs, 3 retrieved-doc-better-than-gold, 2 residual mislabels;
> only 1–2 genuine). True failure mass = GENERATION (13) → **build B1**. Also: ~8 items are
> corr=0 + faith=1.0 (answer grounded in OTHER corpus docs than gold) → 23.8% is a LOWER bound;
> single-gold grading under-credits a redundant corpus. Dumps: `evals/_out_clean_indepjudge.jsonl`,
> `evals/_retrieval_split_clean.jsonl` (gitignored).**
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

**Decision gate (drives which Phase-B lever, or C):**
- Re-run the zero-cost `evals/retrieval_precision.py` split on the new dump → fresh taxonomy
  counts (RETRIEVAL_MISS / GEN_SPECIFICITY / GEN_HALLUCINATION / OK). Command:
  `python -m evals.retrieval_precision --eval-set evals/eval_set_v2_clean.jsonl --sample 40
  --seed 7 --dump evals/_out_clean_indepjudge.jsonl --out evals/_retrieval_split_clean.jsonl`
- **If GEN_SPECIFICITY dominates** → **B1** (reasoning-first scratchpad) first.
- **If GEN_HALLUCINATION / low faith dominates** → **B3** (source_quote grounding) first.
- **If failures are flat across all categories** → run the **B2 format-tax probe BEFORE
  concluding Phase C** — a "flat ceiling" is also exactly what JSON-locked decoding produces;
  the probe is ~$0.05 vs a model swap's ongoing prod cost. Only if B2 shows no lift → Phase C.
- **If the clean+independent number is already materially higher** (e.g. corr ≥ ~50%) → re-baseline,
  re-decide whether any further lever clears the cost/risk bar at all.

---

## Phase B — generation levers, RANKED (BUILD · conditional on A's gate)

> **Revised 2026-06-12 after RAG diagnosis.** Root finding: the whole advisory generates in ONE
> `with_structured_output(AdvisoryDraft)` call (`json_mode` on DeepInfra, `rag.py:609`), and the
> schema's FIRST field is `problem_summary` — the model commits to its answer before any reasoning
> space (field order = generation order). Tam et al. 2024 ("Let Me Speak Freely?",
> arxiv.org/abs/2408.02442) measured ~10–15% reasoning degradation under JSON-locked decoding.
> GEN_SPECIFICITY (right doc retrieved, wrong number stated) is exactly the signature this
> produces. Measure ONE lever at a time, paired, on the Phase-A harness.

### B1 — reasoning-first scratchpad field (cheapest structural lever; GEN_SPECIFICITY)

- **B1.1** Add optional `analysis: str | None = None` as the **FIRST** field of `AdvisoryDraft`
  (`backend/models/advisory.py`) so it generates before everything else.
- **B1.2** One prompt block: fill `analysis` first — quote the exact sentences (rates, products,
  thresholds, conditions) from the retrieved context you will use, then derive the answer fields
  from those quotes. Extend one existing exemplar to model it (exemplars move the needle,
  directives don't — measured L1/L2/L3 pattern).
- **B1.3** Strip `analysis` in `rag.py` post-process (never displayed/stored; keep in eval dumps
  for debugging). Env kill-switch like L3.
- **B1.4** Measure paired A/B on the Phase-A harness (clean set, independent judge, n=40, seed=7).
- **Risk to respect:** `advisory.py:35-44` — extra LLM-filled schema fields previously crashed
  structured output. Mitigations: optional field, no enum/typed structure (plain string), strip
  post-gen, kill-switch; if structured-output breakage reappears → abort lever.

### B2 — format-tax probe: two-step generate→format (EVAL-ONLY probe first; ceiling test)

- **B2.1** Eval-only variant in `answer_eval_full.py` (flag, e.g. `--two-step`): generation call
  WITHOUT structured output (free-form prose answer, same prompt otherwise) → second cheap call
  (Groq `llama-3.1-8b-instant` or Gemini flash) formats the prose into `AdvisoryDraft`.
- **B2.2** Run paired vs one-step on the Phase-A harness. If corr lifts materially (≥ ~10pp, the
  literature range) → the "70B ceiling" was format tax, NOT model capability → productionize
  two-step (latency note: formatting on 8b ≈ 1–2s; unconstrained gen is often *faster*) and
  **Phase C is off the table**.
- **B2.3** If no lift → format tax disproven for this stack; Phase C becomes the live option.

### B3 — L3 Stage-2: verifiable verbatim grounding (`source_quote`; faithfulness-targeted)

The parked Stage-2 of the L3 lever. Makes rate/product specificity **verifiable**, not just
encouraged — structurally lifts faithfulness (the more safety-critical number).

- **B3.1** Add optional `source_quote` (verbatim rate/product string) to each `Product` in
  `backend/models/advisory.py`.
- **B3.2** Zero-cost grounding check in `backend/services/rag.py` post-process: the `source_quote`
  string must appear in a retrieved chunk; if absent → downgrade confidence / flag (do NOT blank —
  guard over-suppression stays closed).
- **B3.3** TDD: unit tests for the grounding check (present/absent/whitespace-drift cases).
- **B3.4** Measure one paired A/B on the Phase-A harness (clean set, independent judge).
- **Same schema-fragility risk + mitigations as B1.** If breakage → directive-only fallback.
- **Note:** B1's "quote exact sentences into `analysis`" is a lite version of this. If B1 wins
  big, B3 may be redundant — re-check before building.

---

## Phase C — Generator model swap (TEST · LAST RESORT — only after B2 disproves format tax)

Only if Phase A shows a flat ceiling AND the B2 probe shows free-form generation does NOT lift
correctness (i.e. the limit really is 70B reasoning/extraction, not JSON-locked decoding).

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
| B1/B3 build + unit tests | no | $0 |
| B1/B3 measure (paired, each) | yes | ~$0.05–0.10 |
| B2 probe (paired, eval-only) | yes | ~$0.05–0.10 |
| C test run | yes | ~$0.05 (+ ongoing if adopted) |

Reference: whole last month of DeepInfra evals = **$0.27**. Cost is small but per the rule each
paid run is OK-gated.

---

## Recommendation

**Phase A is running.** When it lands: re-run the split, let the gate pick B1 / B2 / B3.
Do NOT build any B lever or C before A's gate — risks fixing an artifact. One lever at a time,
each paired on the same harness.

## Revision note (2026-06-12, RAG diagnosis pass)

- Phase A executed with Taiwo's go; `--judge-provider gemini` wired into `answer_eval_full.py`
  (rebinds corr+faith judges AFTER the provider block; quota-fallback also pinned to Gemini so a
  429 can't silently reintroduce the 70B self-judge).
- Phase B restructured from a single lever into a ranked menu (B1 scratchpad / B2 format-tax
  probe / B3 source_quote) after diagnosis: single-call `with_structured_output` + answer-first
  field order are unexamined structural suspects with literature-measured impact in the 10–15pp
  range (Tam et al. 2024). Phase C demoted to last resort behind the B2 probe — "flat ceiling"
  is ambiguous between model limit and format tax, and the probe disambiguates for ~$0.05.
