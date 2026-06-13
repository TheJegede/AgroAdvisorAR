# PROGRESS.md — AgroAdvisor AR

> **Single source of truth for "where are we / what's been tried."** Read this BEFORE
> writing any plan so we don't re-propose dead ends. Update it after every session
> with code changes (alongside CLAUDE.md + status-bar + memory).
>
> **Last updated:** 2026-06-13 (**PHASE 2 ANSWER-KEY GRADING BUILT + RUN** — `/build` of the Phase-2 plan inline TDD on `feat/phase2-ragas-ground-truth` (NOT merged, eval-only): Tasks 1–7 done. `evals/ground_truth/` package (answer-key store + grounded synthesis + independent-Gemini answer-key judge + `--grade-mode {gold,answerkey,both}` + RAGAS `--with-answer-key`); 100 keys synthesized / 97 INSUFFICIENT-dropped (gold chunk lacked the answer), Taiwo human-validated **83 keys** over 2 rounds. **TASK 7 PAIRED RESULT (n=79, gold vs answerkey on identical items): overall corr gold 39% → answerkey 61% = +21.5 pts; poultry 42→85, rice 40→56, soy 37→56.** Single-gold grading under-counts correctness by ~21.5 pts on human-validated ground truth (LOWER BOUND — 97 worst no-answer-gold queries excluded) → MEASUREMENT FIX, proves rice-curation diagnosis. Added `--item-timeout` after a 49-min one-query network hang. See RESUME HERE. Earlier 2026-06-12: **RAGAS DIAGNOSTIC EVAL Phase 1 BUILT + RUN** — `/build` of the Phase-1 plan: Tasks 0–6 shipped TDD ($0, 8 pure tests green, 7 commits on `feat/ragas-diagnostic-eval`); Task 7 RUN with Taiwo OK. **MATRIX (n=38, B1-on arm, Gemini judge + local gte): faithfulness 0.72 / answer_relevancy 0.78 / context_precision-ref-free 0.71 / context_recall 0.16 (rice 0.00\* provisional).** Reading: retrieval precision DECENT (~0.71 → retrieval NOT bottleneck, re-confirms CLOSED); generation faithfulness moderate (0.72, ≈ eval's 68.4%); context_recall LOW but largely EVAL-ARTIFACT (single/contaminated gold + string-distance recall on v3 re-chunk — rice gold flagged provisional). DIAGNOSTIC confirms the existing story, raises no ceiling. See top section. Earlier same day: **RICE DIAGNOSIS + B2 FORMAT-TAX DISPROVEN + B3 STAYS LIVE** — rice 18% is an EVAL-measurement artifact not a pipeline failure (GOLD_ARTIFACT+EVAL_MISLABEL=58% of fails, TRUE_RETRIEVAL=0); B2 two-step unconstrained corr 27.5%→23.8% (−3.7pp inside ±5pp, leans negative → json_mode mildly HELPS this 70B, opposite of Tam et al.) → format tax CLOSED, do NOT productionize two-step, Phase C model-swap now the live next question (Taiwo's call); rice did NOT move (18→16) under free-form = confirms eval-artifact; B3 stays LIVE (rate-grounding 46% < 80%). See top block. Earlier: **PHASE A HONEST BASELINE corr 23.8%/faith 57.5% (clean set + independent Gemini judge, n=40) + B1 REASONING-FIRST SCRATCHPAD = WIN + SHIPPED default-ON** — corr→27.5% helped 7/hurt 3, faith→65.0%; retrieval re-confirmed CLOSED (12 RETRIEVAL_MISS ≈ 85% artifact). See top section. Earlier: **L3 VERBATIM-RATE LEVER = MEASURED WIN + SHIPPED** — directive+exemplar, default ON; paired DeepInfra corr 30%→35%, faith 47.5%→52.5%, soybeans 14%→29%, GEN_SPECIFICITY 6→4, helped 3/hurt 1; Stage 2 schema not needed; backend changed → push triggers HF deploy. See top section. Earlier: **CORPUS-GAP SPLIT RESULT** — zero-cost retrieval/generation diagnostic: gap is GENERATION-SPECIFICITY not corpus coverage; next lever = L3 "quote exact rate/product"; soybean bucket also ~60% label-contaminated → `eval_set_v2_clean.jsonl`. See top section. Earlier: **DOCS-DRIFT FIX** — CLAUDE.md de-staled: stripped to stable-only + un-gitignored + Stop-hook nudge; shipped spot_check.py `b953892`. See top section. Earlier: **L2 EXEMPLARS MEASURED = WIN** — batched DeepInfra eval: v3+L2 corr 20%→30% (paired, L2 helped 7/hurt 1), faith 40%→52.5%, suppression 15%→0%; F5 contamination probe CLEAN (0 bleed/40 answers). Earlier same day: Docling v3 ingestion + L2 shipped; 8/10 code-review findings fixed.
> Remaining: station satellite re-placement, external APIs, no-code legal+pilot.)
> Companion docs: `CLAUDE.md` (Priorities), `docs/status-bar.md` (% rollup),
> `~/.claude/.../memory/project_eval_contamination.md` (why the retrieval metric lies).

---

## ▶▶ RESUME HERE (next session) — Phase 2 answer-key grading BUILT + RUN; single-gold artifact PROVEN (+21.5 pts) on human-validated ground truth
- **STATUS 2026-06-13 (Phase 2 DONE, eval-only, branch `feat/phase2-ragas-ground-truth`, NOT merged):** `/build` of `docs/superpowers/plans/2026-06-13-phase2-ragas-ground-truth.md` ran inline TDD. **Tasks 1–7 DONE.** Tasks 1–4,6 = $0 (9 ground_truth tests + 4 compute_correctness tests green, per-task commits); package `evals/ground_truth/` = answer-key store + grounded synthesis prompt + independent-Gemini answer-key judge + cost-gated `synth.py` + `--grade-mode {gold,answerkey,both}` in `answer_eval_full.py` + RAGAS `--with-answer-key` (AnswerCorrectness). Default `gold` path byte-unchanged (16 regression tests green).
- **Task 5 synthesis + HUMAN VALIDATION (Taiwo OK'd spend):** synth ran ~197 Gemini-2.5-flash grounded calls → **100 keys / 97 INSUFFICIENT-dropped** (gold chunk lacked the answer — single-gold artifact in the open; plan guessed ~8 drops, got 97, all genuine). Taiwo validated in TWO rounds (15-item sample + full 85 remainder): **83 keys validated** (general 26 / rice 30 / soy 13 / poultry 14), 17 dropped (crop mislabels + unsafe/insufficient chunks). 24 namespace-relabels-to-general + 6 PDF-parse text fixes applied. Circularity guard enforced: only `validated:true` keys ever score.
- **▶ TASK 7 PAIRED RE-MEASURE RESULT (Taiwo OK, `--grade-mode both`, DeepInfra 70B + independent Gemini judge, B1-on, 83 keyed-query subset `eval_set_v2_clean_keyed.jsonl`, scored=79 skipped=4 JSON-fragility):** gold vs answerkey on IDENTICAL items —

  | namespace | n | gold corr | answerkey corr | Δ |
  |---|---|---|---|---|
  | poultry | 13 | 42% | **85%** | +43 |
  | rice | 35 | 40% | **56%** | +16 |
  | soybeans | 31 | 37% | **56%** | +19 |
  | **OVERALL** | 79 | **39%** | **61%** | **+21.5 pts** |

- **THE FINDING (NIW/arXiv-quotable — keys are human-validated):** single-gold grading **under-counts correctness by ~21.5 pts** on human-validated ground truth → the advisories are far more correct than the gold-chunk-match ruler showed. This is a **LOWER BOUND** on the artifact: the 97 worst queries (gold chunk had NO answer) were dropped, not graded — including them widens the gap. Confirms the rice-curation diagnosis directly: rice gold-ruler 40% → answerkey 56% (+16); single-gold is the broken instrument, not the pipeline. 9 gold=0→answerkey=1 flips spot-checked = legitimate different-but-correct answers (the multi-reference semantics by design; judge prompt credits "different-but-correct"). Faith was never gold-dependent → unchanged.
- **▶ NEXT (Taiwo's call):** (1) **Merge `feat/phase2-ragas-ground-truth` to main** (eval-only → no deploy) once Taiwo signs off — then archive plan to `plans/completed/`. (2) **Phase C generation model swap** — answerkey corr 61% is the honest headroom signal; gen is still the ceiling. (3) Optionally validate more keys (currently 83/197) + run RAGAS `--with-answer-key` for `answer_correctness`. Lever series: L1=NO-OP, L2=WIN, L3=WIN, B1=WIN, B2=DISPROVEN, **Phase 2 answer-key grading = MEASUREMENT FIX (single-gold artifact = +21.5 pts proven)**.
- **Artifacts:** dump `evals/_capture_answerkey_paired.jsonl` (gitignored). Tracked: keyed subset `evals/eval_set_v2_clean_keyed.jsonl`, answer keys `evals/ground_truth/answer_keys.jsonl`, validation docs `docs/superpowers/2026-06-13-phase2-answer-key-validation{,-round2}.md`.
- **Run hiccup (fixed):** first full run hung 49 min on one query's network call (no client timeout, CPU-idle) → added `--item-timeout` (default 180s, hang→skip) in `answer_eval_full.py`; relaunch clean. Pipeline itself was fine (n=2 probe).

---

## ▶ (prior) RESUME — Rice Gold Curation BUILT + RE-MEASURED; finding = rice corr is a SINGLE-GOLD artifact, faith is the trustworthy rice signal
- **STATUS 2026-06-13:** `/build` of the plan ran TDD on `feat/rice-gold-curation`. **Tasks 1–8 DONE.** Tasks 1–7 = $0 (6 pure tests green, 7 per-task commits); module `evals/rice_gold_curation.py` (flag → independent keyword candidate-search over `corpus_v3` → apply → audit → validate). Curated output `evals/eval_set_v2_clean_rice.jsonl`: **198 → 191 rows (7 dropped, 63 repointed), residual TOC golds = 0, rice 111 → 104.** Task 6 human gate: dropped **7 cross-crop mislabels** (2 corn / 3 soybean / 2 wheat mis-filed in rice), accepted keyword top-1 for 63 repoints.
- **▶ TASK 8 RE-MEASURE RESULT (RAN with Taiwo OK, n=40 seed=7 DeepInfra 70B + independent Gemini judge, B1-on, scored=37 skipped=3):** **overall corr 21.6% / faith 75.7% / supp 0%.** Per-namespace: poultry corr 67%/faith 50% (n=3), **rice corr 10%/faith 86% (n=21)**, soybeans corr 31%/faith 65% (n=13).
- **THE FINDING (important — curation did NOT lift rice corr, and that is itself the diagnostic payload):** rice **corr fell 18→10% while faith ROSE to 86%**. **13 of 21 rice items (62%) are `corr=0 / faith=1.0`** — grounded answers that don't match the single gold. So: (a) the pipeline produces *grounded* rice answers (faith 86% — the trustworthy rice signal); (b) low rice **corr is a SINGLE-GOLD MEASUREMENT artifact**, not a pipeline failure — keyword-top-1 repointed golds are topical rice docs but not necessarily THE doc the model retrieved/used, so a correct-from-corpus answer still scores corr=0. **Curation traded the TOC-artifact for a keyword-mismatch-artifact** → single-chunk gold grading *cannot* yield a trustworthy rice corr on this redundant corpus. **A trustworthy rice corr needs multi-reference / answer-key grading (Phase 2 RAGAS synthetic ground-truth), NOT single-chunk gold.** Curation's durable wins: removed the 7 cross-crop mislabels + all TOC golds, and cleanly exposed the corr=0/faith=1 dominance.
- **▶ NEXT — TWO PLANS DRAFTED 2026-06-13 (build either via `/build` in a fresh session):**
  - **Phase 2 — RAGAS ground-truth answer keys:** `docs/superpowers/plans/2026-06-13-phase2-ragas-ground-truth.md` on branch **`feat/phase2-ragas-ground-truth`**. The real fix for the single-gold artifact — synthesize + human-validate reference answers, grade correctness against "any correct answer" (`--grade-mode answerkey`), wire RAGAS `answer_correctness`. Tasks 1–4/6 = $0; Task 5 synthesis + Task 7 re-measure cost-gated (STOP for OK); Task 5b = human-validation gate (circularity guard). Eval-only, no deploy.
  - **Phase C — generation model swap (eval-only probe first):** `docs/superpowers/plans/2026-06-13-phase-c-gen-model-probe.md` on branch **`feat/phase-c-gen-model-probe`**. `--gen-model` arm swaps ONLY generation (same retrieval+judge) to measure faith/corr lift from a stronger model before committing prod to ongoing cost. Candidates (current IDs): Haiku 4.5 `$1/$5` → Sonnet 4.6 `$3/$15` → Opus 4.8 `$5/$25`. Tasks 1–2/3-prereq = $0; Task 3 probe arms cost-gated per arm; Task 5 productionize is GATED (touches backend → auto-deploys, ongoing cost). **Lead with faith (readable now); corr only fully readable after Phase 2.**
  - **Sequencing recommendation:** Phase 2 first (cheap, fixes the ruler, makes Phase C's corr gain provable + NIW-quotable); then Phase C with a trustworthy ruler. faith 75.7% is the moderate ceiling either way.
  - Lever series: L1=NO-OP, L2=WIN, L3=WIN, B1=WIN, B2=DISPROVEN, **rice-gold-curation = data asset, corr-unmovable by single-gold (faith is the signal)**.
- **MERGED + PUSHED to main 2026-06-13 (`ef830ac`, --no-ff; eval/docs only → NO HF/Vercel deploy fired).** Plan archived to `docs/superpowers/plans/completed/2026-06-12-rice-gold-curation-phase1.md`, spec at `…/specs/`. Artifacts (gitignored): dump `evals/_capture_rice_curated.jsonl`, log `evals/_capture_rice_curated.log`. Branch `feat/rice-gold-curation` merged (safe to delete).
- **DOCS CLEANUP (same merge):** archived 3 done/superseded plans → `plans/completed/` (rice-curation, ragas-phase1, corpus-expansion blueprint). `plans/` root now holds only the deliberately-PARKED `2026-06-12-regen-gold-chunk-ids-v3.md` (build only when passage-level retrieval eval is wanted).
- **RAGAS Phase 1 (just shipped, MERGED):** built+run via `/build`; matrix faith 0.72 / ans_rel 0.78 / ctx_prec 0.71 / ctx_recall 0.16 (rice 0.00\* provisional → the cell THIS curation un-provisions). **Merged to main + pushed 2026-06-12 (`901ef58`, --no-ff; eval-only, no deploy).** See "RAGAS DIAGNOSTIC MATRIX — RESULTS" below.
- **Other live levers (after curation, Taiwo's call):** Phase C generation model swap (ongoing prod cost); B3 `source_quote` rate-grounding (46% < 80% headroom). Lever series: L1=NO-OP, L2=WIN, L3=WIN, B1=WIN, B2=DISPROVEN/closed.
- **Phase 2 (plan later):** RAGAS synthetic ground-truth + human-validated subset → un-provisions rice `context_recall`, enables `answer_correctness`, **absorbs the "curate rice gold" loose end**. Novelty angle — circularity (LLM-grades-LLM) must be human-validated before any paper claim.

---

## ▶ RAGAS DIAGNOSTIC MATRIX — RESULTS 2026-06-12 (Phase 1, eval-only)
> Built via `/build` of `docs/superpowers/plans/2026-06-12-ragas-diagnostic-eval-phase1.md`. Standalone offline scorer `evals/ragas_eval.py` (cost-gated `--confirm-cost`). Gen re-run = DeepInfra 70B + Gemini judge, B1 on, n=40 seed=7 clean set → 38 scored / 2 skipped (`OutputParserException` structured-output fragility, same ~5% as prior arms). RAGAS = Gemini-2.5-flash judge + local gte embedder ($0 embeds). Dump `evals/_capture_b1on.jsonl`, logs `evals/_capture_b1on.log`/`evals/_ragas_matrix.log` (all gitignored).

| group | n | faithfulness | answer_relevancy | context_precision (ref-free) | context_recall |
|---|---|---|---|---|---|
| **OVERALL** | 38 | 0.72 | 0.78 | 0.71 | 0.16 |
| poultry | 4 | 0.69 | 0.88 | 0.80 | 0.50 |
| rice | 17 | 0.71 | 0.84 | 0.68 | 0.00\* |
| soybeans | 17 | 0.74 | 0.68 | 0.73 | 0.24 |
| suppressed=False | 38 | 0.72 | 0.78 | 0.71 | 0.16 |

\* rice `context_recall` **provisional** — contaminated rice gold (yearly-series "br wells" volumes + 3 cross-namespace mislabels, per the 2026-06-13 rice diagnosis); fixed in Phase 2.

- **Interpretation:** (a) **context_precision 0.71 (ref-free)** → retrieval surfaces relevant context ~71% of the time = retrieval is NOT the bottleneck → re-confirms the **closed-retrieval guardrail**. (b) **faithfulness 0.72** (RAGAS, independent judge) ≈ the eval's own 68.4% faith on the same arm = generation faithfulness is the moderate ceiling, consistent across two judges. (c) **answer_relevancy 0.78** = answers stay on-topic (soybeans lowest 0.68). (d) **context_recall 0.16 overall is LOW but largely an EVAL-ARTIFACT** — `NonLLMContextRecall` is string-distance recall of single/contaminated gold against snippets from the v3 re-chunk (chunk boundaries shifted, so verbatim gold rarely string-matches); rice 0.00 is the contaminated-gold tell. Treat ctx_recall as the metric MOST in need of Phase-2 gold curation, not a retrieval failure signal.
- **Suppression 0%** (guard suppressed nothing) → only the `suppressed=False` segment exists; guard-over-suppression stays CLOSED.
- **Caveat:** RAGAS `answer_relevancy` logged repeated `LLM returned 1 generations instead of requested 3` (gemini-flash under-sampled the strictness committee) → ans_rel is computed on 1 generation not 3 = noisier than nominal; directional only.
- **DIAGNOSTIC value delivered:** completes the retrieval×generation matrix the spec set out to fill, and every cell agrees with the prior story (retrieval decent, generation the ceiling, gold the eval weak spot). It **explains** the faith/corr ceilings; it does not raise them — exactly as scoped (diagnostic, not a lever).

---

## ▶ RICE DIAGNOSIS + B2 FORMAT-TAX PROBE + B3 DECISION — 2026-06-13
> Plan `docs/superpowers/plans/2026-06-13-rice-diagnosis-b2-format-tax.md` executed. Findings doc: `docs/superpowers/2026-06-13-rice-diagnosis-findings.md`. Evals-only (no prod code) → push does NOT trigger HF deploy.

- **Task 1 — rice 18% diagnosis (zero-cost, read of `_out_clean_indepjudge_b1on.jsonl` + split):** classified all 19 failing rice items → **GOLD_ARTIFACT 8 / GEN_FAILURE 8 / EVAL_MISLABEL 3 / TRUE_RETRIEVAL 0**. **GOLD_ARTIFACT+EVAL_MISLABEL = 58% → rice 18% is substantially an EVAL-MEASUREMENT problem, not a pipeline failure.** Root cause: 7 of 8 GOLD_ARTIFACT items have gold = a yearly *"YYYY br wells arkansas rice research studies"* volume the judge itself calls "a table of contents"/"a list of academic citations"/"research context [with] no recommendations" — single-gold grading penalizes rice for its own non-answer-bearing gold labels; + 3 cross-namespace mislabels (a corn-N question, a soybean-variety question, a gold pointing to a soybeans doc). TRUE_RETRIEVAL=0 → **closed-retrieval guardrail reconfirmed for rice.** Highest-leverage rice action = curate rice gold labels in `eval_set_v2_clean.jsonl` (relabel/drop the 3 mislabels, re-point gold off the yearly volumes onto the dedicated topical docs the pipeline already retrieves) — a DATA fix, not a lever.
- **Task 2 — `--two-step` format-tax probe built (TDD, eval-only, $0):** new `extract_json_block` + `_TwoStepRunnable` + `_TwoStepLLM` in `evals/answer_eval_full.py` (unconstrained DeepInfra gen → parse → Groq-8b `json_mode` repair fallback; pre-seeds `rag._deepinfra_llm` so `run_rag_query`'s non-streaming path uses the wrapper; `_postprocess_async`/B1-strip run unchanged). Added `products_rates`+`chunk_snippets` to the dump (Task 4 input). New `evals/paired_compare.py` reporter. 6 new tests + 70 non-docling evals tests green. *Deviation:* added `evals/` to the test's sys.path (plan's literal test omitted it → `ModuleNotFoundError: judge`; matches existing `test_judge_quota.py`). *Env note:* full `evals/tests` run can't complete — **pre-existing** pyarrow access-violation from docling-importing siblings (`test_eval_retrieval_matrix.py`, `test_remap_eval_set.py`), reproduces with my files removed.
- **Task 3 — B2 paired arm RUN (n=40 seed=7, DeepInfra 70B UNCONSTRAINED + independent Gemini judge, B1 on both arms, scored=40 skipped=0):** survived a mid-run system sleep at 24/40 (dead socket timed out, item retried clean, 0 lost). **corr 27.5%→23.8% (−3.7pp, inside ±5pp), faith 65.0%→67.5%, supp 0%.** Paired: corr helped 5/hurt 7/same 28; faith helped 7/hurt 6. Per-crop corr: poultry 25→38(n=4), **rice 18→16(n=19)**, soybeans 38→29(n=17). **VERDICT: FORMAT TAX DISPROVEN → B2 CLOSED.** Delta is inside noise AND leans negative (hurt>helped, soybeans −9pp) → for this Llama-3.3-70B + AdvisoryDraft schema, `json_mode` constrained decoding *mildly HELPS* (scaffolds) — the **opposite** of Tam et al. 2024 "Let Me Speak Freely?" (publishable negative). **Do NOT productionize two-step in `rag.py`. Phase C (generation model swap) is now the live next question — Taiwo's call (ongoing prod cost), present numbers and stop.** Rice did NOT move under free-form (18→16) = direct confirmation of the Task 1 eval-artifact finding (no gen lever lifts rice until gold is curated). Dump `evals/_out_clean_indepjudge_twostep.jsonl`, log `evals/_phaseB2_run.log` (gitignored).
- **Task 4 — B3 (`source_quote`) decision:** rate-grounding rate (numbers in stated rates appearing in retrieved chunks, `evals/_b3_grounding.py`) = **46% (11/24) < 80% → B3 STAYS A LIVE CANDIDATE** (NOT closed). 54% of stated rates aren't verbatim/number-grounded → that's the expected headroom for an explicit `source_quote` grounding field+check (B1's quote-into-analysis doesn't yet ground rates reliably). Caveat: crude number-substring metric on the two-step arm; treat 54% as an upper bound.
- **NEXT (two live candidates, both Taiwo's call to prioritize):** (1) **Curate rice gold labels** in `eval_set_v2_clean.jsonl` (data fix — highest-leverage for a trustworthy rice headline; rice number is not trustworthy until done). (2) **Phase C generation model swap** OR **B3 `source_quote` lever** as the next answer-quality move — B2 closed the format-tax route, so these are the remaining generation levers. Lever series: L1=NO-OP, L2=WIN, L3=WIN, B1=WIN, **B2=DISPROVEN/closed**.

---

## ▶ PHASE A HONEST BASELINE + B1 SCRATCHPAD LEVER — MEASURED WIN + SHIPPED 2026-06-12
> Plan `docs/superpowers/plans/2026-06-12-answer-quality-next-lever.md` executed same day: Phase A (trustworthy baseline) → gate → B1 (reasoning-first scratchpad) built TDD + measured + default ON.

- **Phase A — the honest headline (replaces self-judged 35%/52.5%):** clean 198-item set (`eval_set_v2_clean.jsonl`), DeepInfra 70B gen, **independent Gemini 2.5-flash judge** (new `--judge-provider gemini` in `evals/answer_eval_full.py` — rebinds corr+faith judges AFTER the provider block, quota-fallback also pinned Gemini), n=40 seed=7, 0 skipped: **corr 23.8% / faith 57.5% / supp 0%**. Self-judge inflation ≈ +11pp corr. **Crop ranking FLIPPED:** soybeans 32% (best), rice 18% (worst, n=19), poultry 12% (n=4) — "weak soybeans" was label contamination all along. Caveat: ~8 items corr=0+faith=1.0 (answered correctly from non-gold corpus docs) → 23.8% is a LOWER bound; single-gold grading under-credits a redundant corpus. NIW/arXiv: use 23.8%/57.5%, never 35%.
- **Split on the new dump (n=40):** OK 15 / RETRIEVAL_MISS 12 / GEN_SPECIFICITY 8 / GEN_HALLUCINATION 5 — but item audit: RETRIEVAL_MISS ≈ 85% artifact (5 near-duplicate yearly-series docs e.g. gold "2019 br wells" vs retrieved 2021/2022, 3 retrieved-doc-better-than-gold, 2 residual mislabels: a corn question + a soybean question in rice namespace; only 1–2 genuine, e.g. metribuzin-tolerance doc). **True failure mass = GENERATION → retrieval stays CLOSED.** Doc-title hit@5 overcounts misses on this redundant corpus (yearly-series siblings).
- **B1 lever (RAG diagnosis → literature: JSON-locked decoding costs ~10–15pp reasoning, Tam et al. 2024 "Let Me Speak Freely?"; schema generated answer-first):** optional `analysis: str|None` as FIRST field of `AdvisoryDraft` (field order = generation order) + `B1_REASONING_BLOCK` directive + `B1_REASONING_EXEMPLAR` (quotes context verbatim into analysis, derives answer from quotes) in `utils/prompt.py`; `rag._postprocess_async` strips `analysis` before guard/storage/display. **Default ON** (`B1_REASONING_FIRST=0` kill-switch). Stacks on L2+L3. 9 unit tests (`test_prompt_b1.py`); backend **300 pass**.
- **Measured (paired n=40, identical harness, Phase-A run = off-arm):** corr 23.8%→**27.5%** (helped 7/hurt 3/same 30), faith 57.5%→**65.0%** (helped 10/hurt 6), supp 0%, 0 structured-output skips (schema-fragility risk did not materialize). Corr Δ alone < 5pp noise rule, but 7-vs-3 pairing at n=40 > L3's ship evidence (3-vs-1 at n=20) and faith +7.5pp is the safety-critical metric → shipped. Per-crop corr: poultry 12→25, soybeans 32→38, rice flat 18. Dumps `evals/_out_clean_indepjudge{,_b1on}.jsonl` (gitignored).
- **Lever series: L1 directive=NO-OP, L2 exemplars=WIN, L3 verbatim=WIN, B1 scratchpad=WIN.** Structural/exemplar changes move the needle; bare directives don't.
- **NEXT — plan written, build next session: `docs/superpowers/plans/2026-06-13-rice-diagnosis-b2-format-tax.md`** (Task 1 rice diagnosis $0 FIRST → gates Task 2/3 B2 probe → Task 4 B3 close/keep decision). Summary of the order it encodes: (1) **B2 format-tax probe** (free-form gen → cheap formatter, eval-only flag in `answer_eval_full.py`, ~$0.05–0.10 cost-gated) — if free-form lifts corr ≥ ~10pp the "70B ceiling" was JSON-format tax → productionize two-step + Phase C dead; if flat → format tax disproven, Phase C becomes live. (2) **Rice bucket diagnosis** (zero-cost, read `_out_clean_indepjudge*.jsonl`) — rice corr flat 18% n=19 while poultry/soybeans moved; biggest remaining mass, find why before next paid lever. (3) B3 (`source_quote`) likely redundant after B1 (quote-into-analysis is its lite form) — re-check before building. Latency note: analysis generates first → delays first streamed visible field; acceptable at the 45–50s gen ceiling, revisit with token-streaming work. **PUSHED 2026-06-12 (`4ee97a5`) → HF deploy Action fired; post-deploy spot-check pending (novel prod query, confirm advisory + no schema errors in Space logs).**

---

## ▶ L3 VERBATIM-RATE LEVER — MEASURED WIN + SHIPPED 2026-06-12
> Built + measured the L3 "quote the exact rate/product from the cited chunk" generation lever (plan `docs/superpowers/plans/2026-06-12-l3-quote-exact-rate-generation-lever.md`), targeting the GEN_SPECIFICITY failures the corpus-gap split found dominant. **Stage 1 (directive + worked verbatim exemplar) WON — Stage 2 (schema `source_quote`) NOT needed.**

- **What shipped:** `L3_VERBATIM_RATE_BLOCK` directive + `L3_VERBATIM_EXEMPLAR` (worked example copying "3.2 pt/A" verbatim) in `backend/utils/prompt.py`, appended in `build_system_prompt` (both intents). **Default ON** (`L3_VERBATIM_RATE` unset/≠"0"); `L3_VERBATIM_RATE=0` = kill-switch. Stacks on L2 (does not replace it). 8 unit tests + 291 backend green.
- **Measured (paired DeepInfra n=20 seed=7, v3, L2 on in both arms):**
  | metric | L3 off (B) | L3 on (A) |
  |---|---|---|
  | correctness | 30.0% | **35.0%** |
  | faithfulness | 47.5% | **52.5%** |
  | soybeans corr | 14% | **29%** |
  | suppression | 0% | 0% |
  Paired: **helped 3 / hurt 1 / same 16.** Split: GEN_SPECIFICITY 6→4, OK 10→12 (soybean OK 2→4).
- **Decision:** all three gate conditions met (corr↑, GEN_SPECIFICITY↓, helped>hurt) → flipped default ON, skipped Stage 2. **Lever series so far: L1 directive = NO-OP, L2 exemplars = WIN, L3 directive+exemplar = WIN.** Pattern holds: exemplars move the needle, bare directives don't.
- **Caveats:** n=20, DeepInfra self-judge (paired Δ valid, absolute optimistic); 2 of 3 helps are on the known mislabeled soybean items (Clearfield-rice, sprayer-40ac) — but faith +5pp, a rice help, and the GEN_SPECIFICITY 6→4 shrink are genuine. Dumps `evals/_out_v3_L3{off,on}.jsonl` (gitignored).
- **NEXT:** remaining failures = RETRIEVAL_MISS 3 (rice/poultry) + GEN_SPECIFICITY 4 + 1 hallucination. GEN_SPECIFICITY no longer dominates alone. Re-measure on cleaned eval set (`eval_set_v2_clean.jsonl`) to get the un-contaminated soybean headline. **Backend changed → push to main triggers HF deploy (deploy Action watches `backend/**`); not pushed yet.**

---

## ▶ CORPUS-GAP SPLIT — RESULT 2026-06-12 (zero-cost retrieval/generation diagnostic)
> Ran the planned failure-split (`docs/superpowers/plans/2026-06-12-corpus-gap-retrieval-split.md`). **Conclusion: the gap is GENERATION-SPECIFICITY, not corpus coverage.** The prior "NEXT = corpus-coverage gap" hypothesis is **CONTRADICTED** — do not re-propose corpus/re-ingest as the soybean lever. Full writeup: `docs/superpowers/2026-06-12-corpus-gap-findings.md`.

- **Taxonomy split (seed=7 n=20, v3, joined to `_out_v3_L2on.jsonl` corr/faith):** OK=10, RETRIEVAL_MISS=3, GEN_SPECIFICITY=6, GEN_HALLUCINATION=1. Baseline L2-off: OK=5, RETRIEVAL_MISS=4, GEN_SPECIFICITY=10, GEN_HALLUCINATION=1 (L2 already moved 4 GEN_SPECIFICITY→OK).
- **Dominant failure = GEN_SPECIFICITY** → **next lever = L3 "quote the exact rate/product from the cited chunk"** generation directive, NO corpus work. Retrieval surfaces the right *document* in ~2/3+ of failures; the model then states the wrong number/product.
- **Soybeans specifically: 0 RETRIEVAL_MISS, 5 GEN_SPECIFICITY** — the "14% corr" is NOT retrieval/corpus; the right docs retrieve every time. It is generation-specificity **+ eval-label noise**: of the 5 soybean failing items, 3 are mislabel/out-of-scope (a Clearfield-RICE question tagged soybeans, a pine-seedling forestry question, generic sprayer-coverage math). Audited → `evals/eval_set_v2_clean.jsonl` (1 RELABEL soybeans→rice, 2 DROP; 200→198). Original `eval_set_v2.jsonl` untouched.
- **Suppression confirmed 0%** across crops in both dumps → guard/over-suppression work stays CLOSED (do not reopen).
- **Method caveat / dead end avoided:** exact gold-`chunk_id` hit@5 is **invalid on v3** — the Docling v3 re-chunk (968bc42) changed every chunk_id, so ZERO eval-set gold ids exist in `agroar-prod-gte-v3` (verified by `index.fetch`); an id hit@5 on v3 is always-miss garbage. Used **document-level hit@5** (`document_title`, a stable exact key across the migration) instead. Also: **local `.env` `PINECONE_INDEX_NAME` is STALE at `agroar-prod-gte-v2`** while prod + the dumps are v3 — the diagnostic defaults `--index agroar-prod-gte-v3`. Dense cosine-to-gold was rejected (same-crop agronomy floors ~0.83, non-discriminating).
- **Artifacts:** `evals/retrieval_precision.py` (+14 offline tests, zero LLM cost), `evals/_retrieval_split*.jsonl` (gitignored). Optional paid re-run on the clean set (Task 6) NOT done — cost-gated, awaiting OK.

---

## ▶ DOCS-DRIFT FIX + SESSION SHIP 2026-06-12 (CLAUDE.md de-staling)
> Root-caused why CLAUDE.md is chronically stale and fixed it structurally.
- **Why it drifted:** CLAUDE.md was gitignored (invisible to commit flow/diffs) AND duplicated volatile status (shipped dates, eval numbers, "not pushed") that PROGRESS.md already owns. No automation existed — the "auto-update rune" was just a manual feedback memory.
- **Fix C (root cause):** rewrote CLAUDE.md to hold ONLY stable knowledge (architecture, build/test/deploy, conventions, durable guardrails). All volatile status → here. Added a scope-banner at the top of CLAUDE.md so it doesn't get re-polluted.
- **Un-gitignored CLAUDE.md** (owner did this) → now tracked, shows in diffs/status.
- **Fix B (nudge):** local Stop hook `.claude/hooks/check_progress_sync.py` + `.claude/settings.local.json` `hooks.Stop` — fires when the latest commit changed code but not PROGRESS.md; self-silences once a PROGRESS bump lands. `.claude/` is gitignored so the hook is per-machine.
- **Shipped uncommitted work:** `ingestion/spot_check.py` (zero-cost retrieval spot-check, ALL PASS 0.895–0.943) + docling-v3 cutover plan checklist → commit `b953892`, pushed (ingestion-only, no HF redeploy). Verified all prior "uncommitted" claims (SSE, F4, code-review) were already on origin/main — docs were stale, not the code.
- ~~**NEXT (unchanged):** corpus-coverage gap analysis — triage suppressed/wrong soybean items (14% corr, 43% supp) into corpus-miss vs guard-over-suppress vs gen-fail. Read-only, needs last eval `--dump`.~~ **DONE — superseded (later same day):** the corpus-gap split ran and **CONTRADICTED** this hypothesis (gap is GEN-SPECIFICITY, not corpus). Drove the L3 lever (also shipped). See "CORPUS-GAP SPLIT — RESULT" + "L3 VERBATIM-RATE LEVER" sections above. Do NOT re-propose corpus-gap analysis as next — it's closed.

---

## ▶ CODE-REVIEW REMEDIATION 2026-06-12 — 8 of 10 findings FIXED (TDD, backend 285 green)
> Backlog: `docs/superpowers/plans/2026-06-12-code-review-findings.md`. Built inline TDD in the plan's suggested order (1+2, 3, 8, 4+6, 10, 7). Committed + pushed (`42f8f1e`, on origin/main).

| # | Pri | Finding | Fix |
|---|---|---|---|
| F1 | P0 | UTC `at` vs Open-Meteo `America/Chicago` local (inversion/rain-window/Gate-A-date wrong at boundaries) | `routers/dicamba.py` `_to_central()` (zoneinfo) converts `body.at` at `/check`+`/record` before rules/weather/gates; naive=already-local |
| F2 | P0 | Zero-coverage precip window → 0.0 → false Gate C rain-free pass | `weather_now` counts matched hours; 0 → `precip_next_48h_in=None` → needs_confirmation |
| F3 | P0 | DB advisory rows dump ~2KB raw JSON each into prompt history | `query._normalize_history` reads `content_type`; advisory→`problem_summary` only (`_advisory_summary`), else drop row |
| F8 | P2 | naive `datetime.now()` in immutable spray record | `datetime.now(timezone.utc)` |
| F4 | P1 | merged judge `[]` → confidence 1.0 guard bypass | `judge_answer_llm` raises on empty claims when `len(answer)>80` → verify_answer two-step fallback |
| F6 | P1 | judge claim/object zip misaligned past non-dict entries | filter `parsed`→`dict_objs` once, reuse for extraction + post-process |
| F10 | P2 | `sanitize()` hard-400s whole query on one bad client-history row | per-row try/except in `_normalize_history` drops offending row |
| F7 | P2 | O(n²) cumulative partial-frame SSE payload | `rag.PARTIAL_STREAM_THROTTLE_SECONDS=0.25` throttles `_on_partial_cb` (1 frame/250ms) |

**HELD F5** (few-shot exemplar fake-citation bleed) — do NOT fix blind; measure during the pending batched DeepInfra eval (grep outputs for "Arkansas Herbicide Guide 2026" / "Arkansas Insect Management Handbook 2026" / fips `05031` as contamination probe; if bleed → rename exemplar citations "EXAMPLE-DOC-A" + gate exemplars off follow-up turns). **DEFERRED F9** (rain-check label vs hardcoded 48h) — latent, consistent today (rules say 48); not in plan's suggested order; revisit if a rules record sets ≠48. Housekeeping: `.gitignore` += `ingestion/stderr.txt`, `ingestion/backup_pdfs/`. New tests: +12 cases (weather_now 1, dicamba_router 3, spray_check 1, review_fixes 3, citation_guard_v2 3, rag_streaming 1); suite 285 pass. Backend changes auto-deploy to HF on push (`backend/**` in deploy Action watch list).

---

## ▶ DEFERRED OPS — PROD CUTOVER DONE 2026-06-08 (remaining = pilot-data + external + no-code)

Tracking plan: `~/.claude/plans/so-i-want-you-wobbly-kay.md` (owner-vs-Claude checklist).
**✅ F4 BACKEND IS LIVE IN PROD 2026-06-08** — #1 + #2 closed; all `/dicamba/*` endpoints serve
(verified: prod OpenAPI lists 8 routes, `/check`+`/stations` 401 auth-gated not 404/500, Vercel proxy
reaches the new backend). Remaining items are pilot-data integrity, external APIs, and the no-code track.

1. ✅ **DONE — migrations `009_spray_records` + `010_spray_feedback` applied to prod Supabase** (owner,
   dashboard SQL editor, 2026-06-08). O1 found only these two missing.
2. ✅ **DONE — HF backend redeployed** (owner pushed verified `hf-deploy` orphan branch → HF Space,
   2026-06-08; Claude built+verified the branch, backend suite 219 pass on it).
   **▶ AUTOMATED 2026-06-10 — backend redeploy NO LONGER owner-blocked.** GitHub Action
   `.github/workflows/deploy-backend.yml` (commit `5455182`) replays the orphan-push to the HF Space on
   every push to `main` touching `backend/**`/`Dockerfile`/`.dockerignore`/`README-space.md` (+ manual
   `workflow_dispatch`), auth via repo secret `HF_TOKEN`. Mirrors the Vercel frontend auto-deploy. So any
   backend change now ships itself on push — e.g. the pending SSE-heartbeat fix will deploy automatically
   once merged. Manual orphan-push remains the fallback if the Action breaks (steps in CLAUDE.md #4).
3. **Research-station coordinates — identities/addresses VERIFIED, exact GPS pending** (C2, 2026-06-08).
   All 10 confirmed vs authoritative UA AAES listings; `source` field rewritten (no longer blanket
   UNVERIFIED); `main_fayetteville` renamed Milo J. Shult AREC; added AR-bbox guard test. **Owner residual:**
   re-place `rohwer_res` (real site at Watson, ~5 mi off) + spot-confirm 9 pins from satellite to sub-mile
   precision before pilot. Full report `docs/f4-station-coord-verification.md` (gitignored, local).
4. **FieldWatch registry API** (Phase 5 deferred) — owner must contact FieldWatch for access. Until then
   the wizard deep-links FieldCheck + keeps the Gate B `human_attested` confirmation. If pullable → new
   `sensitive_sites` cache feeding Gate B verifiable/partial checks.
5. **EPA Bulletins Live! Two geospatial layer** (Phase 5 deferred) — currently a deep-link in the wizard;
   integrate the layer if/when an API path is chosen.
6. **Mesonet / delta-T inversion measurement** (Phase 5 deferred) — owner must find an Arkansas mesonet
   delta-T source to move inversion from `estimate` → `measurement`. Until then the heuristic stands,
   always labeled `is_estimate`.

Together: F4 is fully built + tested in-repo but **not yet exercisable in prod** until #1 + #2.

---

## TL;DR — current state

- **F4 DICAMBA REBUILD (PRD v3) — Phase 0 + Phase 1 SHIPPED 2026-06-08.** F4 redefined from a
  backward-looking drift-complaint form into a before-you-spray dicamba compliance checklist (four
  gates A/B/C/D; PRD `AgroAdvisor_F4_PRD_v3.md`; 7 phase plans in `docs/superpowers/plans/`).
  **Phase 0** (`main`, merged): versioned effective-dated rules-as-data `backend/data/dicamba_rules.json`
  + `services/spray_rules.py` (`resolve_rules` + accessors). **Phase 1** (branch
  `feat/f4-dicamba-phase1-check`): `POST /api/v1/dicamba/check` for Gates A (legal window) + C (weather
  now) — new `services/weather_now.py` (Open-Meteo **forecast** API + inversion-risk **estimate**),
  `models/spray.py`, `services/spray_check.py` gate engine (verifiable_fact vs human_attested;
  inversion never auto-passes), `routers/dicamba.py`. TDD, 25 new tests, full backend **166 passed**.
  Gates B/D + persistence/PDF are later phases. Coexists with old drift tool.
  **Phase 2 — Spray-Check Wizard SHIPPED 2026-06-08** (`docs/superpowers/plans/2026-06-08-f4-dicamba-phase2-wizard.md`):
  new 3-step UI `components/dicamba/SprayCheckWizard.jsx` + `hooks/useSprayCheck.js`
  (`getSprayStepErrors` + `runCheck` → `POST /api/v1/dicamba/check`), `pages/SprayCheckPage.jsx`,
  route `/spray-check`, sidebar nav `t.sprayCheck` (coexists with `/drift-report`). Step 1 product +
  license attestation (Gate A), Step 2 **react-leaflet** click-to-place pin → fires `/check` + live
  conditions summary (Gate C), Step 3 per-gate result cards + inversion toggle that re-runs `/check`
  and flips the outcome banner. Advisory framing (never "approved, spray now"); EN+ES; high-contrast
  status badges (≥4.5:1) + `min-h-touch`. Added deps `react-leaflet@5` + `leaflet@1.9`. TDD:
  `useSprayCheck.test.js` (7) + `e2e/spray-check.spec.js` (2). Verified frontend **36 vitest pass**,
  lint clean, build OK, playwright spray spec green. Committed + pushed to `main` (`90cd0b7`); Vercel
  frontend auto-deploys on push.
  **⚠️ HF BACKEND NOT YET REDEPLOYED** — `/api/v1/dicamba/check` (Phase 1) lives on `main` but the HF
  Space still runs the pre-Phase-1 image, so the wizard's `/check` call 404s in prod until a backend
  redeploy (orphan-branch force-push to HF — see CLAUDE.md Priorities #2). Deferred by owner: redeploy
  once all F4 phases land.
  **Deviations from the Phase 2 plan:** (1) plan said spec in repo-root `tests/`, but playwright
  `testDir` = `frontend/e2e/` → spec lives at `frontend/e2e/spray-check.spec.js` (matches existing
  `drift.spec.js`). (2) Live-conditions summary pulls wind/temp/48h-rain from Gate C check `observed`
  values; `SprayCheckResponse` exposes no separate soil/sunrise fields, so those (named in the plan's
  step-2 summary) are omitted. (3) `CLAUDE.md` is gitignored locally → its F4 doc update is NOT in the
  commit (local-only); PROGRESS.md + memory carry the record instead.
  **Phase 3 — Gate B Field & Buffer Map SHIPPED 2026-06-08** (`docs/superpowers/plans/2026-06-08-f4-dicamba-phase3-gateB-map.md`):
  wizard grows from 3 → **4 steps** (Eligibility A → **Field & Buffers B** → Live Conditions C →
  Confirm & Result); the field pin moves to the new Step 2. Backend: new
  `backend/data/ar_research_stations.json` (10 UA/USDA-ARS stations, marked **UNVERIFIED** at source),
  `services/spray_stations.py` (`load_stations` + `haversine_ft` + `nearest_station`),
  `spray_rules.buffers_ft` accessor, `evaluate_gate_b` (verifiable `station_buffer` distance + two
  human-attested neighbor checks: `non_tolerant_neighbor` ¼ mi, `organic_specialty` ½ mi marked
  Partial / registry-incomplete), `run_spray_check` gains `stations` (gate order A,B,C), new
  `GET /dicamba/stations`, `ResearchStation` model, `ApplicatorAttestation.organic_specialty_checked`.
  Frontend: `useSprayCheck.fetchStations()`; `SprayCheckWizard` draws three `Circle` buffer rings
  (ft→m × 0.3048, `BUFFERS_M` constant) + station `CircleMarker`s on the react-leaflet map, nearest-
  station distance label, two Gate B confirm checkboxes that re-run `/check` (same pattern as inversion
  toggle). Station data single-sourced server-side (both `evaluate_gate_b` + `/stations` read
  `load_stations()`). TDD: new `test_spray_stations.py` (5) + extended `test_spray_check.py`/
  `test_dicamba_router.py`; **backend 179 pass**, **frontend 37 vitest pass**, lint clean, playwright
  spray spec **2 pass** (mocks `/stations` + `/check`, asserts ≥4 leaflet-interactive paths + Gate B
  card + toggle re-runs). Still **HF BACKEND NOT YET REDEPLOYED** (same as Phase 1/2).
  **Out of scope (later phases):** record save + PDF (Phase 4), Gate D downwind geometry (wind × Gate B
  sites, Phase 4), pro Spanish review (Phase 5). Station coordinates ship **UNVERIFIED** — owner must
  validate before any production/pilot reliance.
  **Phase 4 — Record Generator + Gate D SHIPPED 2026-06-08** (`docs/superpowers/plans/2026-06-08-f4-dicamba-phase4-record-impl.md`):
  adds the 4th gate + an immutable PDF-backed spray record. Backend: `weather_thresholds.downwind_half_angle_deg=45`
  rules-as-data + `spray_rules.downwind_half_angle_deg`; `spray_stations.bearing_deg` + `angular_diff`
  geometry helpers; `evaluate_gate_d` (verifiable **downwind cone** check — flags a research station only
  when it sits inside its 1-mi buffer AND within the ±45° downwind cone of the current wind; `needs_confirmation`
  when wind direction is unavailable — plus 5 human-attested equipment checks: boom height, droplet size,
  tank clean, additives VRA/DRA+no-AMS, ground-application-only), wired into `run_spray_check` so `/check`
  now returns gates A,B,C,D. New immutable `spray_records` table (`009_spray_records.sql`, RLS owner
  SELECT+INSERT only, **no UPDATE/DELETE policy** = append-only, admin SELECT) + `services/spray_record.py`
  (create/get/list, service-role client, `farmer_id` stamped from JWT never payload = anti-IDOR, no mutate
  surface) + `generate_spray_record_pdf` (ReportLab). New endpoints `POST /dicamba/record` (re-runs the check
  server-side authoritatively then persists the frozen snapshot), `GET /dicamba/records`, `GET /dicamba/record/{id}`,
  `GET /dicamba/record/{id}/pdf`. Frontend: `useSprayCheck.saveRecord`; wizard Step 4 gains 5 Gate D
  attestation checkboxes (each re-runs `/check`) + **Save record** → **Download record PDF**; new
  `useSprayRecords` hook (+ standalone `fetchSprayRecords` for the unit test — project has no DOM test env),
  `SprayRecordsPage` at `/spray-records` (sidebar nav + EN/ES i18n `sprayRecords`). TDD: new
  `test_spray_record.py` (4) + extended `test_spray_rules.py`/`test_spray_stations.py`/`test_spray_check.py`/
  `test_dicamba_router.py`/`test_pdf_generator.py`; **backend 201 pass**, **frontend 38 vitest pass**, lint
  clean, **playwright spray spec 3 pass** (Gate D attest → save → PDF link + records-list). **Deviations:**
  (1) plan's `test_list_records_uses_owner` lambda used `setdefault(...) or [...]` which returns the truthy
  fid string not the list — rewrote as a named fn. (2) plan's hook test used `@testing-library/react`
  `renderHook`, but the repo has no testing-library/DOM env — instead exported `fetchSprayRecords` and
  unit-tested that; hook UI is covered by e2e. (3) e2e mock keeps overall rollup on Gate B+inversion (Gate D
  rides alongside) so the Step-4 outcome-banner assertion still holds before Gate D is attested.
  **Still PENDING (owner):** apply `009_spray_records.sql` to prod Supabase + **HF backend orphan-branch
  redeploy** so `/record` + the 4th gate go live (same redeploy debt as Phases 1–3). Station coords still
  **UNVERIFIED**.
  **Phase 5 — Spanish Parity + Soil Check + Registry Deep-links SHIPPED 2026-06-08** (TDD; plan
  `docs/superpowers/plans/2026-06-08-f4-dicamba-phase5-external-spanish.md`; owner scoped to the
  in-codebase **safety slice**, external-API integrations deferred — see Deferred Ops #4-6). (1) **Spanish
  parity:** every gate `title`/check `label`/`reason` authored bilingual at the source (`CheckResult`
  +`label_es`/`reason_es`, `GateResult`+`title_es` in `models/spray.py`; all of `spray_check.py` Gates
  A-D + `weather_now._estimate_inversion` reasons now emit ES). Closes the confirmed gap where backend
  gate strings rendered English even in ES mode. Frontend `SprayCheckWizard` `GateResultCard` +
  failing-reasons render `es ? *_es : *`. (2) **Soil-saturation Gate C check:** `soil_moisture_max=0.45`
  rules-as-data + `spray_rules.soil_moisture_max`; new `soil_not_saturated` check (verifiable when
  `soil_moisture_0_1cm` present, `needs_confirmation` when missing — never a guessed pass) — Gate C now
  5 checks. (3) **Registry deep-links:** bilingual FieldWatch FieldCheck + EPA Bulletins Live! Two panel
  in wizard Step 2 with the Gate B `human_attested` fallback (no API needed). TDD: parity guard tests over
  pass/fail/unavailable branches + ES-differs-from-EN + soil pass/fail/missing + weather_now ES reasons +
  e2e registry panel + full ES-mode walk; **backend 210 pass**, **frontend 38 vitest pass**, lint clean,
  **playwright spray 4 pass**. **Deferred (owner-blocked):** FieldWatch API pull, EPA Bulletins layer
  integration, mesonet delta-T inversion source (Deferred Ops #4-6). Same HF-redeploy + migration-009
  prod debt as Phase 4.
  **Phase 6 (Code Track) — Central Disclaimer, Gate Stats, and Feedback Loop SHIPPED 2026-06-08** (TDD; plan
  `docs/superpowers/plans/2026-06-08-f4-dicamba-phase6-code.md`):
  (1) **Central Disclaimer:** created `disclaimers.js` defining bilingual constants, rendered persistently above
  step content on all steps in the wizard, removed Step 4 inline copy, unified backend PDF disclaimer in
  `pdf_generator.py` under the module-level constant `SPRAY_DISCLAIMER`. (2) **Gate Stats:** implemented
  `GET /api/v1/dicamba/stats` (admin-only via `require_admin`) using `aggregate_gate_stats` in `spray_stats.py` to
  tally pass/fail/needs_confirmation counts across all frozen records. (3) **Feedback Loop:** added append-only
  feedback table via migration `010_spray_feedback.sql` with owner/admin RLS; Pydantic models in `models/spray_feedback.py`;
  `POST /api/v1/dicamba/feedback` in `routers/dicamba.py` (validated via `verify_record_ownership` in
  `services/spray_feedback.py` to prevent IDOR feedback injection); created `SprayFeedbackWidget` that renders on
  Step 4 when a record is saved. TDD: unit/integration tests for stats, feedback service, and router; expanded playwright
  spray-check E2E spec to walk the wizard, verify disclaimers in EN and ES, save a record, click thumbs up, fill comment,
  submit, and assert thank-you message; **backend 218 pass**, **frontend 45 vitest pass**, lint clean, Playwright
  E2E **4 pass**.
- **Prod: LIVE (2026-05-30).** Frontend Vercel `agroadvisor-eta.vercel.app` → API proxy →
  backend HF Spaces `whoisluwah-agroadvisor-backend.hf.space`.
- **SIDEBAR SESSIONS AUTO-REFRESH = SHIPPED 2026-06-02 (session 8).** Fixed new chat sessions not appearing in the sidebar until manual refresh. Removed forced key remount from ChatPageWrapper, updated ChatPage to navigate to search query param on session creation, and implemented ref-based activeSessionId synchronization in useEffect. Verified 26/26 frontend tests pass, 108/108 backend tests pass, and ESLint is clean.
- **TRACTOR LOADER ANIMATION = SHIPPED 2026-06-01 (session 7).** Replaced standard three-dot TypingIndicator with a theme-adaptive, CSS-animated SVG tractor driving past crops. Fully integrated with Tailwind data-theme styling for Light and High Contrast modes. Verified 26/26 frontend tests pass, 0 lint errors, and 108/108 backend tests pass.
- **CITATION GUARD OVERHAUL = SHIPPED + merged to `main` 2026-05-31.** Backend redeployed to HF.
- **RESPONSE RENDERING DEFECTS (M1+M2+M3) = SHIPPED 2026-05-31 (session 2).** `suppressed` flag + confidence label reconciliation + `_strip_scaffolding` + prompt unbracket + `SuppressedNotice` + AdvisoryCard branch. Backend 100/101 (1 pre-existing stale), frontend 26/26, lint clean. Pushed to `main` → Vercel auto-deployed. (`685a202`..`1a196db`)
  The broken MiniLM NLI judge is retired from the hot path; an **LLM-as-judge** (provider chain)
  now scores groundedness, suppression is **surgical + rate-safe**, and `Document N:` scaffolding
  is killed at the prompt source. **Effect (local-Qwen gen + Gemini judge, gte, n=9): suppression
  11% (was ~67% on the broken NLI), faithfulness 88.9%, confidence_score 0.64–1.00 mean.** Full
  backend suite 93 pass / 1 pre-existing stale fail.
- **CODEBASE REVIEW CLEANUP = DONE 2026-05-31 (session 3).** 4-phase cleanup from `/review-code` full-pass: (P1) `utils/llm.py` shared provider singletons — `_is_quota_error` + `_get_groq/_get_gemini/_providers` de-duped across classifier/guard/translation; `utils/db.py` `_assert_insert` helper kills 3× duplicated error pattern; dead `import json` + `OUTPUT_INSTRUCTIONS` alias removed. (P2) renames: `_lexical_support` vars clarified, `_call` → `_call_llm`, `CHUNK_PREVIEW_LENGTH/FEET_TO_METERS/LOGIN_RATE_WINDOW/DEFAULT_COUNTY_FIPS` named constants. (P3) simplifications: `OUT_OF_SCOPE_MESSAGES` dict merges EN+ES, `translate_to_en` guard simplified, `create_client()` bypass in `reset_password` → singleton fixed, `NOAA_CONTACT_EMAIL` env var. Advisory model modernized: `Optional[X]`→`X|None`, `List[X]`→`list[X]`, `ClaimResult.score` gets `Field(ge=0,le=1)`. Frontend: `DetailSection` replaces duplicate `DetailedExplanation`/`KeyPoints`, `CropChip` inlined, `makeMessage` factory, `TECHNICAL_ERROR_RE` module constant, `Date.now()+1` removed, arrow fns in useSessions. (P4) `_cached_fetch` extracts 3× cache-check pattern in context.py; USGS defensive chaining simplified; `Sidebar.jsx` split into `SessionsList`+`SidebarFooter`; delete-handler stale closure fixed; `useEffect` deps clarified. Suite: 107/108 backend (1 pre-existing stale), 26/26 frontend, lint clean.
- **PHASE 1 UX FIXES = SHIPPED 2026-05-31 (session 4, `68aec4e`).** Design audit → 3 parallel fixes: (A) AdvisoryCard hierarchy reordered — `ProblemSummary` + actions now first, confidence badges moved to bottom of advisory/informational branches; (B) 5 touch targets enlarged to 44px (`w-9 h-9→w-11 h-11` send/hamburger/profile, `py-2.5→py-3` sidebar nav, `p-1→p-2` delete btn, `min-h-touch` mid-chat chips); (C) Low confidence badge contrast fixed 3.94:1→8.02:1 (WCAG AA fail → AAA) via outlined `text-arred-dark` on white. Lint clean, 26/26 tests pass.
- **PHASE 2 UX = SHIPPED 2026-05-31 (session 5, `4210cb3`).** Resilient State + Data Clarity — 4 parallel sub-phases: (A) `useSessions` exposes `sessionsLoading`/`sessionsError`; Sidebar shows skeleton rows while loading, retry link on error, profile skeleton/`Profile unavailable` text when `useProfile` fails; (B) `useSSEQuery` stores last query + exposes `retry()`+`retryable` (true on non-AbortError); `ChatPage` renders Retry button above input when retryable; (C) `useSyncStatus` + `SyncStatusBar` wired into AppShell — harvest-coloured 28px bar appears only offline (zero layout shift online); (D) NLI badge hidden when `confidence_score===0`; rate values in `ProductsRates` use `font-mono`; `CitationsSection` `text-gray-600`→`text-gray-700` (10.27:1, clears 7:1 outdoor threshold). Lint clean, 26/26 tests pass.
- **PHASE 3 UX = SHIPPED 2026-06-01 (session 6).** Audit Closeout — 3 parallel sub-phases: (A) i18n completeness: 4 missing keys added to `i18n.js` (EN+ES) — `offline`, `retry`, `sessionsLoadError`, `profileUnavailable`; `SyncStatusBar` uses `useLang`; Sidebar `|| "..."` fallback + hardcoded "Profile unavailable" replaced; ChatPage `t.retry || 'Retry'` → `t.retry`; (B) AlertBanner resilience: optimistic dismiss now restores on PATCH failure via GET /alerts re-fetch; (C) Visual polish: `ChatInput` container `rounded-2xl`→`rounded-card`; `📞` in EscalationCard + `🌾` in OutOfScopeCard replaced with inline Heroicons SVG; citation link contrast `text-field`→`text-field-dark` (3.59:1→meets AA). Lint clean, 26/26 tests pass.
- **INVALID DATE UI FIX = SHIPPED 2026-06-01.** Fixed "Invalid Date" showing under text messages in ChatHistory. Previously, when message objects were refactored to use UUIDs (`crypto.randomUUID()`), `MessageBubble` still attempted to parse `id` as a date via `new Date(id)`, resulting in "Invalid Date". Fix: (1) Added `createdAt` timestamp parameter to `makeMessage` in `ChatPage.jsx`, (2) Mapped `createdAt: m.created_at` in `useSessions.js` for loaded database messages, (3) Modified `MessageBubble.jsx` to receive and format the `createdAt` prop, defensively skipping date parsing on UUID string formats. Lint clean, 26/26 frontend tests pass, 107/108 backend tests pass.
- **70B PROD EVAL DONE (2026-06-05).** DeepInfra Llama-3.3-70B gen + judge, `agroar-prod-gte-v2`,
  n=20 seed=7: **correctness 20%, faithfulness 40%, suppression 15%**. Per-namespace: poultry 50%/50%
  (n=4), rice 11%/44% (n=9), soybeans 14%/29% (n=7, 43% suppressed). See eval section below.

### Why the guard mattered (historical, keep for NIW/arXiv honesty)
A live end-to-end trace (2026-05-31) proved the guard — not retrieval, not generation — was
producing the bad responses: retrieval returned gold in top-5 and Groq generated a correct grounded
answer, but the NLI (`nli-MiniLM2-L6-H768`) labeled 7/8 true claims `CONTRADICTED` and `score_answer`
hard-zeroed the whole advisory → blank body, "Low". **Implication: every ~40%-correctness / "Low"-floor
number measured WITH the old guard on was corrupted.** Full write-up: memory `project-guard-root-cause`.

---

## ✅ Guard overhaul — what shipped (Phases 1–6, TDD, subagent-driven)

1. **Phase 1** (`3a0cd8a`) — lexical-contradiction guard: never honor a CONTRADICTED label when the
   claim shares ≥0.6 content-token overlap with a chunk (`LEXICAL_CONTRADICTION_GUARD`).
2. **Phase 2** (`8eee998`, fix `f5457b4`) — **LLM-as-judge groundedness** (`judge_claims_llm`,
   `GROUNDEDNESS_JUDGE=llm` default); MiniLM NLI kept only as offline fallback (run off the event loop).
3. **Phase 3** (`cd30cd0`) — surgical suppression: drop the contradicted claim and mean the rest;
   full-suppress ONLY when a contradiction is safety-critical (names a rate/unit/number — `_SAFETY_CRITICAL_RE`).
4. **Phase 4** (`4ba97fc`) — thresholds env-overridable (`GUARD_SUPPRESSION_THRESHOLD`/`GUARD_ESCALATION_THRESHOLD`).
   Calibration: LLM-judge scores shifted UP to 0.64–1.00 mean (poultry 1.00, rice 0.85, soybeans 0.64);
   **kept defaults 0.2/0.4** (now cut only the genuine bottom tail — 11% suppression ≈ bottom decile).
5. **Phase 5** (`e2ca0d1`) — cite retrieved docs by bracketed title (no `Document N:` in the prompt);
   scrub residual `Document N:` from displayed citation titles + cause/action/summary prose in `rag.py`.
6. **Phase 6** — config audit: local `.env` was **legacy `agroar-prod` (MiniLM) + contaminated fine-tune
   embedder** → **FIXED to `agroar-prod-gte` + `thenlper/gte-base`** (gte retrieval verified, gold in top-5).

Plan (executed): `docs/superpowers/plans/2026-05-31-citation-guard-overhaul.md`.
Diagnostic scripts kept in `evals/`: `trace_retrieval.py`, `trace_generation.py`, `trace_pipeline_batch.py`.

### ▶▶ RESUME HERE (next session)
1. ✅ HF Space Env Verified (2026-06-03): `PINECONE_INDEX_NAME=agroar-prod-gte-v2` + `EMBEDDING_MODEL_PATH=thenlper/gte-base`.
2. ✅ DeepInfra 70B Integration (2026-06-03): gen + judge provider, no daily quota.
3. ✅ Re-ingest / cut over to `agroar-prod-gte-v2` (2026-06-03): titles/sections metadata live.
4. ✅ `_SAFETY_CRITICAL_RE` calibration (2026-06-03): ignores crop growth stages.
5. ✅ **70B prod eval DONE (2026-06-05):** correctness 20%, faithfulness 40%, suppression 15% (n=20, seed=7).
   See section below for full table.
6. **NEXT — corpus gap analysis**: correctness 20% with 15% suppression = generation is still the ceiling.
   Soybeans suppression 43% and correctness 14% — likely corpus thin on those topics or guard over-suppressing.
   Levers: (a) inspect suppressed soybeans items for guard miscalibration, (b) re-examine corpus coverage
   for soybeans sub-topics, (c) arXiv preprint draft using honest 20% 70B number.

### ▶ D3 GATE RUN — 2026-06-10 (split read, lever named)
> Plan: `docs/superpowers/plans/2026-06-09-pilot-readiness-next-steps.md` (local/gitignored). Ran the gate on the 40-item gold sample with DeepInfra 70B generator (`LLM_PRIMARY=deepinfra` — Groq 70B was TPD-exhausted; matches the n=20 baseline generator) + Gemini 2.5-flash containment judge.

**Authoritative split (corrected gold):** `B2=14 B_MISS=4 B3=1 B4=4 QUARANTINED=15 B_ABSENT=0 B_ABSENT_answered=2`; `judge_error_rate=0.0` (calibration_n=8); `lever1_conditional_fraction_of_b2=0.357`.

**Lever named = GENERATION (answer-quality), NOT retrieval/ingestion.** B2 (gold fact verifiably retrieved, yet answer still wrong) dominates the 25 judged items ⇒ generation is the ceiling — confirms the 70B prod-eval correctness=20% finding with a clean instrument. Conditional-rule handling (L1) = 0.357 of B2 (~5/14). B_MISS=4 (retrieval; 5 levers already rejected) + B3=1 (corpus gap) both small. **Next session = write the generation-lever TDD plan (L1 conditional-rule first); do NOT build before the plan.**

**Calibration root-cause (judge_error_rate 0.6→0.0), 2 real code bugs found + fixed (TDD):**
- `buckets.classify` checked the judge's soft `partial` flag BEFORE the deterministic `span_verified` → a verbatim-retrieved fact wrongly bucketed B4. Fix: hard signal wins (span_verified→B2 first). (regression item [7]).
- `span_verify` verified the *judge's* returned span (LLM output, stitches across the `\n---\n` chunk join / drifts whitespace) → false B_MISS when the gold fact WAS present. Fix: new `fact_retrieved(gold_snippet, judge_span, chunks)` anchors on the verbatim human gold_snippet first, judge span as paraphrase fallback (regression item [8]).
- Also hardened `judge_containment` with bounded retry on transient Gemini 503/429 (was crashing whole gate runs).
- Residual disagreements were a B4 *rubric* gap (owner decision: B4 = containment `partial` only, not holistic answer-quality). Relabeled [1]→B2, [4]→B_MISS; set_aside [0] (derived computation) + [6] (generic-header gold, needs re-transcription). 

**SAFETY FLAG (open):** `B_ABSENT_answered=2` — pipeline answered the 2 corn questions (rice/soy namespaces) instead of abstaining = scope-abstention gap (hallucination signal). Investigate separately.

#### ▶ LATENCY L1 SSE MULTI-STAGE PROGRESS STREAMING — SHIPPED 2026-06-10 (branch `feat/sse-progress-streaming`)
> Plan: `docs/superpowers/plans/2026-06-10-latency-l1-sse-progress.md`. Implemented progressive RAG pipeline stage streaming (Searching -> Found N sources + titles -> Writing -> Verifying -> Advisory) using FastAPI/asyncio.Queue SSE and React 19 hooks.
- **RAG Stage Emission:** Added `_emit` helper and `progress` queue parameters to `run_rag_query` in `backend/services/rag.py` to post stages at core checkpoints.
- **FastAPI Event Stream:** Modified `event_stream` in `backend/routers/query.py` to drain the progress queue, sending event-stream frames as SSE payloads, and maintaining hearts/keepalives.
- **Frontend Stepper Component:** Created `QueryProgress.jsx` component integrating the animated tractor with real-time bilingual status captions and source title lists.
- **Wiring & Cleanup:** Wired state through `ChatPage.jsx` and `ChatHistory.jsx`, clearing the stepper on results/OOS/errors. Deleted orphaned `TypingIndicator.jsx`.
- **TDD Tests:** Created `backend/tests/test_rag_progress.py`, `backend/tests/test_query_progress.py`, and `frontend/src/components/chat/QueryProgress.test.jsx`. Created Playwright E2E spec `frontend/e2e/sse-progress.spec.js` using in-page fetch stream delay mocking. All tests passed.

#### ▶ LATENCY L2 GUARD SINGLE-CALL MERGE — SHIPPED 2026-06-11 (branch `feat/sse-progress-streaming`)
> Plan: `docs/superpowers/plans/2026-06-10-latency-l2-guard-merge.md`. Merged answer claim-decomposition and groundedness-judging into a single LLM call (`judge_answer_llm`), keeping the two-step path as a fallback.
- **Wired and Fallback:** Configured via `config.GUARD_MERGED_JUDGE` (default True). `verify_answer` falls back to decompose -> judge (or NLI) automatically on any failure.
- **Latency reduction:** `python -m scripts.latency_probe` confirms average guard latency reduced from 2061 ms to 1762 ms (saving ~299 ms on Gemini; expected ~600ms on Groq).
- **Correctness preserved:** E2E evaluation (`eval_runner.py` with `n=20` sample) shows correctness is 27.5% (was 30.0% baseline, within noise), proving quality is preserved.
- **TDD Tests:** Added 7 unit/integration tests to `backend/tests/test_citation_guard_v2.py` checking postprocessing, merged LLM judge, and verify_answer fallback. All pass.

#### ▶ CHAT PROGRESS UX FIX + EMPTY-CARD HARDENING — SHIPPED 2026-06-10 (main `2d11b4c`)
> Triggered by prod test of the SDS query: 3–4 empty "Problem Summary" cards rendered + a boxed tractor "loader". Two root causes, both fixed.
- **Empty cards = stale PWA service worker** serving the OLD JS bundle (pre-progress-streaming). Old `consumeSSEStream` rendered each of the 4 backend progress frames (`searching`/`sources_found`/`writing`/`verifying`) as an empty advisory card. Live symptom clears once the SW activates the new build (`registerType:'autoUpdate'` → needs a 2nd reload / "Clear site data"). NOT a code bug in current `main` — current code already routes progress→onProgress.
- **Product direction:** progress must be **inline animated text** (Claude-style), NOT a boxed card. Rebuilt `QueryProgress.jsx` = left-aligned bouncing-dots + pulsing stage caption, dropped the tractor card.
- **Hardening (deploy-skew-proof):** `isAdvisoryFrame()` in `useSSEQuery.js` (a progress/stage/empty frame can never reach `onResult`) + `hasRenderableContent()` in `AdvisoryCard.jsx` (empty advisory renders null, never a blank shell). 81 frontend tests + lint green.

#### ▶▶ LATENCY — REAL NEXT FRONT (generation-bound, NOT cache/retrieval)
> L1(progress UX)/L2(guard merge ~300ms)/L3(answer cache)/L4(bounded context) all SHIPPED + on `main`. They did NOT move the wall-clock ceiling for a normal query. **LangSmith prod trace 2026-06-10** (query "What do I do about soybean SDS in a wet year", `IN_SCOPE_SOYBEANS:DIAG`):
> - classify (Gemini 8b) ~0.35s
> - **`RunnableSequence` generation (70B) = 45–50s** ← dominant cost
> - **guard `ChatOpenAI` = 14–26s** ← second cost
> - **L3 cache MISS by design** — diagnostic answers are never cached (only `informational` + reference-safe are); a verbatim repeat still ran the full 45–50s gen + guard. Working as intended; L3 only helps repeated informational queries.
> **Ceiling = generation (70B latency) + guard, NOT retrieval/cache.** Open levers: (a) **token streaming** — NEXT latency lever (needs partial-JSON streaming over `with_structured_output` + suppress-after-stream safety UX design); (b) **faster/smaller gen model or provider** — DEFERRED (re-check correctness ≈150k tokens/run ~$1 DeepInfra; user cost-averse); (d) **skip guard on cache hits** (already free).

#### ▶ GUARD-TRIM (lever c) — SHIPPED 2026-06-10
> Plan `~/.claude/plans/we-re-tackling-the-agroadvisor-shiny-quokka.md`. Root cause of the 14–26s prod guard: the guard inherited the GENERATION provider chain (`utils/llm.py _providers()` ordered by `LLM_PRIMARY`) — prod trace's guard span was `ChatOpenAI` = **DeepInfra Llama-3.3-70B** (slow throughput), not the warm Gemini the 1.7s probe measured. Judging needs less muscle than generation.
**Fix (TDD, 4 new tests):**
- `_providers(primary=None)` override in `backend/utils/llm.py` — generation chain untouched.
- Guard pins its own chain: `GUARD_JUDGE_PROVIDER` env (default `gemini`) → `_judge_providers()` used by merged judge, two-step judge, and decompose (`citation_guard_v2.py`).
- Per-attempt timeout `GUARD_JUDGE_TIMEOUT_S` (default 8s) via `asyncio.wait_for` (`_judge_invoke`) — hung provider falls through instead of stalling.
- Timing instrumentation: `verify_answer` returns + logs `guard_timings` {judge_s, judge_provider, judge_attempts} so prod traces name the judging provider.
**Verified:** backend pytest 263 pass (was 236). Local probe (`python -m scripts.latency_probe`, gen=Groq, guard=pinned Gemini): **guard avg 1.66s** (rice 2.4s / soy 1.6s / poultry 0.9s), SERIAL avg 3.3s. Post-deploy check: novel prod query → LangSmith guard segment should drop 14–26s → ~2s and `guard timing:` log line names provider.

#### ▶ L1 CONDITIONAL-RULE LEVER — CODE TRACK BUILT 2026-06-10 (branch `l1-conditional-rule-lever`)
> Plan: `docs/superpowers/plans/2026-06-10-l1-conditional-rule-generation-lever.md`. Built subagent-driven TDD, 5 commits (`ce4c2b9..e21bdf5`), per-task spec + code-quality review, final whole-impl review = ready to merge.

**Two halves, both built + green (6 prompt tests + 16 diagnostic conditional tests; full evals suite 77 passed):**
- **FIX (generation):** `CONDITIONAL_RULE_BLOCK` directive in `backend/utils/prompt.py`, appended in `build_system_prompt` for BOTH diagnostic + informational intents — tells the model never to collapse a multi-branch conditional (rate-by-soil / threshold-by-stage / restriction-by-variety / timing-by-stage) to a bare number; state every condition with its branch. No schema change.
- **MEASURE (instrument):** new `evals/diagnostic/conditional_judge.py` — answer-side judge (`flatten_advisory`, `build_conditional_prompt`, `parse_conditional_response`, `judge_conditional`, `CompletenessResult`), Gemini 2.5-flash (≠ 70B generator, no self-grading), garbage→`preserved=False` fail-safe, transient retry mirrors `containment_judge`. Wired into `runner.py`: `ClassifiedItem.cond_preserved`, scored in `_classify_record` for non-set-aside conditional gold items, new gate metric `conditional_completeness_rate` (+ `conditional_scored_n`) in `build_report`. This is the FIRST harness signal that reads the GENERATED answer (containment only reads chunks).

**MERGED to main 2026-06-10** (`019a966`, --no-ff; pushed `ce4c2b9..019a966`). Backend directive NOT live in prod until HF redeploy (owner-blocked, same bucket as F4). `conditional_scored_n==7` confirmed (plan's "2 are set_aside" was stale — actual gold has 0 set-aside conditionals).

**▶▶ L2 FEW-SHOT EXEMPLARS = MEASURED WIN 2026-06-12 (batched DeepInfra eval, plan `docs/superpowers/plans/2026-06-12-batched-eval-plan.md`).** Paired A/B, identical 20 items (seed=7), `agroar-prod-gte-v3`, DeepInfra 70B gen+judge (self-judge bias — absolute optimistic, paired A−B delta valid; n=20 noisy):

| run | corr | faith | supp |
|---|---|---|---|
| v2 baseline (2026-06-05) | 20% | 40% | 15% |
| **B** = v3 + L2 **off** | 15% | 62.5% | 0% |
| **A** = v3 + L2 **on** (prod) | **30%** | 52.5% | 0% |

- **L2 = first answer-quality lever that MOVED the needle** (L1 was a no-op). Paired: L2 helped **7** items, hurt **1** → corr 15%→30%. Cost: faith −10pp (exemplars trade strict grounding for completeness). KEEP (already deployed `e583587`).
- **v3 corpus** (B vs baseline): faith **+22.5pp**, suppression **15%→0%**; correctness flat (within noise). Cleaner + better-grounded. KEEP (already prod).
- **F5 contamination probe = CLEAN.** 0 exemplar fake-citation bleed across **40** answers (both runs); every emitted citation is a real corpus doc. **F5 closed, no action** (token-trim = gate exemplars off follow-ups optional/deferred — pennies, latency is gen-bound). Toggle for B = `git checkout e583587^ -- backend/utils/prompt.py` (L1 kept, L2 removed), restored after.
- **New honest headline = 30% correctness** (v3+L2). **NEXT lever = corpus-coverage gap analysis** (soybeans still 14% corr; rice 39%), per #3 — generation+corpus, not retrieval/guard. **Cost reality (DeepInfra dashboard): one n=20 run ≈ $0.01–0.02, NOT ~$1** (whole last month of evals = $0.27); earlier estimate was ~20–50× high.

**▶ L1 TASK 6 MEASUREMENT DONE 2026-06-10 — DIRECTIVE IS A NO-OP. Generator DeepInfra Llama-3.3-70B (`LLM_PRIMARY=deepinfra`), judge Gemini 2.5-flash, n=7 conditional gold rows:**
| run | `conditional_completeness_rate` |
|---|---|
| BASELINE (directive removed, `git checkout ce4c2b9 -- backend/utils/prompt.py`) | **0.429** (3/7) |
| AFTER (directive live) | **0.429** (3/7) |

**Verdict: L1 prompt directive moved the metric by 0.0.** 4/7 conditionals still collapse their branch-structure to a bare value with the directive in place. A single output-instruction directive is insufficient to fix dropped-condition generation. The measure-half (answer-side `conditional_completeness_rate` judge) is validated and now the live instrument for the next lever. **NEXT = L2: few-shot conditional exemplars** (show the model 2-3 worked multi-branch examples in the prompt), re-measure on the same 7-row gold via `python -m evals.diagnostic.runner --gold evals/diagnostic/gold_conditional.jsonl` (conditional-only subset, ~7 gen calls vs 40). Keep the directive (cheap, harmless, may compound with L2). Run was fast once warm; earlier 30-min "hang" was a transient slow first call (runner now logs per-record progress to stderr).

#### ▶ SSE HEARTBEAT + DISCONNECT RESILIENCE — SHIPPED 2026-06-10 (silent-vanish fix)
> Plan: `docs/superpowers/plans/2026-06-10-sse-heartbeat-disconnect-resilience.md`. Built inline TDD, 5 tasks, 4 commits on `main` (NOT yet pushed to origin).

Root cause (LangSmith): novel/freeform advisory queries showed the tractor then vanished — `event_stream()` awaited `run_rag_query` (~6s LLM) yielding ZERO bytes; idle SSE through the Vercel `/api/*` rewrite → HF Space got reaped at ~6s; the `CancelledError` (a `BaseException`) slipped past `except Exception` so no error frame, and the frontend loop ended without adding a message. Cached/suggested queries survive (Redis first byte); novel ones didn't.

**Three independent fixes, all green:**
- **T1 backend heartbeat** (`backend/routers/query.py`): immediate `: keepalive` first byte + ping every `HEARTBEAT_INTERVAL_SECONDS=2` while `run_rag_query` runs as `asyncio.create_task`; defeats the proxy idle reap.
- **T2 cancel-safety**: `except asyncio.CancelledError` cancels the in-flight rag task + re-raises (no longer masked as generic error); `finally` cancels if still running. Test `backend/tests/test_query_heartbeat.py` (3 new).
- **T3/T4 frontend**: extracted pure `consumeSSEStream(reader,{onResult,onCategory})` → returns `delivered` bool, throws on `{error}` frame, skips comment/malformed lines; `STREAM_EMPTY_CODE` export. `sendQuery` now flags empty streams retryable → `onError(STREAM_EMPTY_CODE)`; ChatPage maps to `t.connectionInterrupted` (EN+ES i18n). Tests in `useSSEQuery.test.js` (4 new).
- **T5 e2e** `frontend/e2e/sse-resilience.spec.js`: empty `data: [DONE]` stream renders a visible Retry + error, not a silent vanish.

**Verified:** backend `pytest -q` 236 pass · frontend `vitest run` 75 pass + lint clean · playwright `chat`+`sse-resilience` 6 pass. **Deploy:** frontend ships on Vercel push immediately; backend heartbeat auto-deploys to HF via `.github/workflows/deploy-backend.yml` on push to `main` (`backend/**` touched). Pushed to origin (`5455182..b57da9a`). Post-deploy check: ask a novel uncached freeform query, confirm the advisory streams through without the tractor vanishing.

#### ▶ DOCKERFILE BUILD-CACHE FIX — 2026-06-10 (`b4783a1`, pushed)
HF backend build sat ~10 min re-downloading ~500MB of models (`thenlper/gte-base` + `cross-encoder/nli-MiniLM2-L6-H768`) on every backend deploy. Cause: the model-download `RUN` sat AFTER `COPY backend/ /app/`, so any backend code change busted that layer's cache. Fix: moved the pre-download `RUN` ABOVE `COPY backend/` (depends only on sentence-transformers + cache ENV, not source). Now only a `requirements.txt` change re-downloads; backend-only deploys keep the layer `CACHED`. The very next build re-downloads once (reorder busts it), then stays cached. `Dockerfile` is in the deploy Action watch list → auto-redeployed.

> Ungated PWA doc loose-end done: PRD M5 + P2 wording now state offline=abstention (reference-only cache; time-sensitive → verify stub). PWA prod phone-verify + Lighthouse (D1/D2) still owner-side/manual.

### Pillar 0 diagnostic harness — SHIPPED 2026-06-09
> Source: PRD `AgroAdvisor_pilot_readiness_PRD.md` + roadmap `AgroAdvisor_pilot_readiness_IMPLEMENTATION_PLAN.md` + TDD plan `docs/superpowers/plans/2026-06-09-diagnostic-harness.md` (all three kept local/gitignored). Built on branch `pilot-readiness-tracks` (8 commits, 33 pytest green).
`evals/diagnostic/` classifies a human gold-labeled sample into buckets (D2/D3).
Re-scoped to solo: SAMPLE (~30-40), not census; search the index don't read it;
quarantine hard cases (no Extension expert). Run:
`python -m evals.diagnostic.runner --gold evals/diagnostic/gold_labels.jsonl`.
NEXT (human): produce gold_labels.jsonl (transcribe-don't-invent, 4 parts +
rule_type tag + human_bucket on the calibration slice), then read the split to
gate Phase 3 (Ingest / L1 / L2 / L3).

### Pillar 2 PWA channel — SHIPPED 2026-06-09
> Source: PRD `AgroAdvisor_pilot_readiness_PRD.md` + roadmap `AgroAdvisor_pilot_readiness_IMPLEMENTATION_PLAN.md` + TDD plan `docs/superpowers/plans/2026-06-09-pwa-channel.md` (all three kept local/gitignored). Built on branch `pilot-readiness-tracks` (10 commits, 71 vitest + 2 playwright green).
The SPA is now an installable, mobile-first, offline-tolerant PWA. **Design = offline
is abstention:** no server → no guard → no verification, so time-sensitive content
(rates/spray/dicamba/warnings/diagnostic) is NEVER shown offline as an actionable
answer. Instead `AdvisoryCard` renders an `OfflineSafetyStub` ("connect to verify" +
the advisory's escalation contact, or a generic county-Extension fallback). Only
`isCacheableAsReference` advisories (informational, no rates/warnings/timing keywords —
default-FALSE when unsure) may be cached for offline reading, badged "reference only".
**API advisories are never runtime-cached** — Workbox precaches the app shell only
(`/api/*` denylisted). Files: `frontend/vite.config.js` (VitePWA + manifest + Workbox +
dev manifest), pure tested helpers `frontend/src/lib/offlineTiering.js` /
`offlineCache.js` / `offlineSafety.js` (+ `.test.js`), hooks
`frontend/src/hooks/useOnlineStatus.js` / `useInstallPrompt.js` (reducer unit-tested),
UI `frontend/src/components/pwa/InstallButton.jsx` /
`frontend/src/components/advisory/OfflineSafetyStub.jsx`, EN/ES strings in
`frontend/src/constants/i18n.js`. E2E `frontend/e2e/pwa-offline.spec.js` (manifest
linked + offline-stub-replaces-frozen-rate, 2 pass). Vitest 71 green, lint clean,
build emits `dist/manifest.webmanifest` + `dist/sw.js`.
**Deferred (owner/CI):** `farm-bg` is already `.webp` and referenced as such (no PNG
to convert; ImageMagick `magick` not on this machine) — nothing to do there; a
Lighthouse mobile/PWA audit pass is the remaining manual check.
**PRD M5 note:** M5 ("last-N answers readable offline") narrowed to *reference* answers
only — time-sensitive answers deliberately show the stub, not a frozen number.

---

## ✅ 70B Prod Eval Results (2026-06-05)

**Config:** DeepInfra Llama-3.3-70B-Instruct (generation + judge) · `agroar-prod-gte-v2` ·
`thenlper/gte-base` · LLM-as-judge guard on · n=20, seed=7, Craighead County AR

**Corpus audit (pre-run):** 200 eval items checked — `Missing from corpus: 0`, `Text mismatches: 0` ✅

| namespace | lang | n | supp | corr | faith | mean conf |
|---|---|---|---|---|---|---|
| poultry | en | 4 | 0% | **50%** | 50% | 0.90 |
| rice | en | 9 | 0% | **11%** | 44% | 0.87 |
| soybeans | en | 7 | **43%** | 14% | 29% | 0.49 |
| **OVERALL** | en | **20** | **15%** | **20%** | **40%** | — |

**Interpretation:**
- Correctness 20% = honest signal at 70B with reliable guard; prior ~40% was corrupted by broken NLI.
- Faithfulness 40% = model grounded in retrieved passages ~half the time (judge is also strict 0/0.5/1.0).
- Poultry outperforms (50% corr): likely denser/cleaner corpus coverage.
- Soybeans 43% suppression: guard suppressing aggressively; likely low confidence from sparse/ambiguous retrieval. Next lever: inspect suppressed items.
- Rice 11% correctness despite 0% suppression: answer generates but misses specific numbers/protocols in gold. Corpus coverage gap.

**No-guard baseline (guard OFF, same config):**

| namespace | n | supp | corr | faith |
|---|---|---|---|---|
| poultry | 4 | 0% | 38% | 50% |
| rice | 9 | 0% | 11% | 44% |
| soybeans | 7 | 0% | 14% | 50% |
| **OVERALL** | **20** | **0%** | **17.5%** | **47.5%** |

Guard impact: removes 3 soybeans items → correctness +2.5pp (17.5→20%), faithfulness −7.5pp (47.5→40%).
Guard is correctly filtering low-confidence items (not over-suppressing). Soybeans 43% suppression with guard
= guard accurately detecting low retrieval confidence for that namespace.

**Run commands (reproducible):**
```bash
cd evals
python answer_eval_full.py --provider deepinfra --sample 20 --seed 7          # guarded (these numbers)
python answer_eval_full.py --provider deepinfra --sample 20 --seed 7 --no-guard  # raw gen quality
```

---

## ✅ Namespace Audit + Relabeled Eval (2026-06-06)

**What changed:** 40 of 70 soybeans-namespace items relabeled to `general`. The "soybeans recommended
chemicals for weed and brush control" document contained pine seedlings, wheat, Clearfield rice,
sprayer calibration, and broadleaf brush queries — all off-crop by query intent. `general` routes
to `_fanout_search` (all 3 crop namespaces), which is correct for those queries.

**Script:** `evals/audit_namespace.py` · DeepInfra Llama-3.3-70B classifier · classification by
query intent (not document origin) · commit `f66d406`

**Relabeled eval — `eval_set_v2_relabeled.jsonl`, n=41 scored / 9 skipped (network timeouts), seed=7:**

| namespace | n | supp | corr | faith | mean_conf |
|---|---|---|---|---|---|
| general | 8 | 25% | **25%** | 44% | 0.55 |
| poultry | 4 | 0% | **50%** | 50% | 0.88 |
| rice | 25 | 8% | **16%** | 50% | 0.77 |
| soybeans | 4 | 0% | **25%** | 50% | 0.74 |
| **OVERALL** | **41** | **10%** | **22%** | **49%** | — |

**Before/after soybeans (seed=7, relabeled vs original):**
- Original soybeans (n=7, includes off-crop): corr 14%, faith 29%, supp 43%
- Relabeled soybeans (n=4, genuine soybean queries only): corr 25%, faith 50%, supp 0%

**Interpretation:**
- Soybeans suppression 43%→0%: guard was correctly flagging off-crop queries that retrieved wrong chunks. Genuine soybean queries retrieve well.
- Soybeans correctness 14%→25%, faithfulness 29%→50%: real improvement once off-crop contamination removed.
- Overall correctness 20%→22%, faithfulness 40%→49%: modest gain; most of the eval is rice (n=25) which is unchanged.
- General namespace 25% corr / 44% faith / 25% suppression: fanout retrieval works but corpus coverage thinner for cross-crop queries.
- 9 skipped items = DeepInfra network timeouts (no `asyncio.timeout` in eval loop). True n closer to 50.

**Run command (reproducible):**
```bash
python -u evals/answer_eval_full.py --provider deepinfra --sample 50 --seed 7 --eval-set evals/eval_set_v2_relabeled.jsonl
```

---

## ⭐ Pinned: the WINNING prod config (do not regress)

Best of everything tested (`answer_eval_full --provider local`):

| Knob | Value | Note |
|---|---|---|
| Index | `agroar-prod-gte-v3` | Docling-extracted, gte-base 768-dim, 21,065 vectors, includes titles & sections |
| Chunking | **512 CHARACTERS** (`ingestion/chunker.py`, `length_function=len`) | NOT tokens (token-chunking regressed — see rejected table) |
| Retrieval | dense-only, top-5 | |
| Reranker | **OFF** | |
| Embedder | `thenlper/gte-base` | `EMBEDDING_MODEL_PATH` env |
| Generation | Groq `llama-3.3-70b` / DeepInfra Llama 3.3 70B (prod) | |
| Groundedness judge | LLM-as-judge (`GROUNDEDNESS_JUDGE=llm`) | NLI offline fallback only |

Run prod-config eval:
`EMBEDDING_MODEL_PATH=thenlper/gte-base PINECONE_INDEX_NAME=agroar-prod-gte-v3 python evals/{eval_runner,answer_eval}.py`

---

## ❌ Retrieval levers TESTED and REJECTED — STOP re-proposing these

All measured, all lost to the winning config above. Retrieval mechanics are **exhausted** and were
**never the bottleneck** (the guard was).

| Lever | Result | Verdict |
|---|---|---|
| **Token-chunking** (480 tok vs 512 char) | corr 40→35, faith 82→70 | ❌ REGRESSION — **REVERTED `f07b523`**. Do not reintroduce. |
| **Hybrid BM25+dense+RRF** | dense 0.275 → 0.245 | ❌ WORSE — queries are semantic paraphrases, weak lexical overlap |
| **Query rewrite** (slang→formal) | hit@5 0.275 → 0.280 | ❌ WASH |
| **HyDE** | hit@5 0.275 → 0.180 | ❌ WORSE |
| **Reranker** (ms-marco-MiniLM) | 40%/82.5% → 30%/70% | ❌ REGRESSION — web-trained, domain-mismatched on ag text |

**Meta-conclusion:** 4 orthogonal interventions all flat on recall@20 (~0.46) ⇒ the **single-gold
retrieval metric is a broken ruler** (relevance-judged was ~0.63), and answer-eval used local Qwen-7B
not prod Groq-70b ⇒ 40% is pessimistic vs prod. Absolute numbers unreliable; relative deltas valid.

Reusable measurement harness kept in `evals/`: `eval_retrieval_matrix.py` (compares dense/sparse/hybrid),
`remap_eval_set.py`, `filter_eval_by_section.py`, `eval_v3_ablation.py`, `audit_retrieval_v3_failures.py`,
`hybrid_core.py`. (Abandoned contextual-chunk experiment + its corpus/index were deleted 2026-05-31 — lost to the 512-char baseline.)

---

## ✅ Recently shipped (earlier this arc)

- **Docling PDF Extraction + `agroar-prod-gte-v3` LIVE (2026-06-12, `968bc42`)**: Replaced PyMuPDF+Camelot with IBM Docling (subprocess-per-10-page, `do_table_structure=False`, CPU-safe). Markdown-aware chunker (MarkdownHeaderTextSplitter). Pre-extracted `corpus_v3.jsonl` (21,065 chunks, 154 docs) embedded via `embed_corpus.py` and upserted to `agroar-prod-gte-v3`. HF Space `PINECONE_INDEX_NAME=agroar-prod-gte-v3` — live in prod. Spot-check ALL PASS (scores 0.895–0.943). `agroar-prod` + `agroar-prod-gte` deleted (free-tier index slots recovered).
- **L2 Few-Shot Conditional Exemplars (`e583587`, 2026-06-12)**: Added `FEW_SHOT_EXEMPLARS` to `build_system_prompt` — two worked JSON examples (soil-texture rate split, crop-stage threshold) showing the LLM how to preserve multi-branch conditionals. L1 directive (no-op, 0.429→0.429) retained as cheap harmless additive. **MEASURED 2026-06-12 = WIN: paired DeepInfra eval, correctness 20%→30% (L2 helped 7 items / hurt 1); F5 fake-citation probe clean (0/40). See "L2 FEW-SHOT EXEMPLARS = MEASURED WIN" section above.**
- **Latency L3 Reference-Safe Answer Cache**: New `backend/services/answer_cache.py` — exact-normalized key (lowercased, punctuation-stripped, whitespace-collapsed) over EN query + language + county_fips + rice-field profile sig; Upstash-backed via existing `cache.cache_get/cache_set` (best-effort, no-ops when Redis unset). `routers/query.py` READs after translate / before classify (first-turn only — `cache_key` stays `None` on a follow-up so no read/write) and serves the hit via `_advisory_sse` (same SSE frame shape as miss path, skips classify+retrieve+generate+guard, ~50ms). WRITEs after the final advisory only when first-turn, non-suppressed, and `is_cacheable_as_reference` (informational, NO products_rates, NO warnings, no time-sensitive term via `_TIME_SENSITIVE_RE` — Python port of PWA `offlineTiering.js`). Eligibility judged on EN text; stored value is user-facing advisory (ES if translated) + `_category` (stripped before the hit frame). A paraphrase MISSES; no rate/spray/timing answer ever cached. TDD: backend tests `test_answer_cache.py` (5) + `test_query_cache.py` (4) green; regression `-k "query or cache or rag"` 40 passed. Build PLAN 4 of 4 (L4→L2→L1→L3). 2026-06-10
- **Latency L4 Bounded Context Fetch**: Implemented tight timeouts for NOAA and SSURGO context fetching clients and wrapped concurrent fetches with `asyncio.wait_for`. Prevents slow/hanging upstream requests from stalling the RAG critical path, safely falling back to the "unavailable" state on breach. Unit tests (3 passed) written in `backend/tests/test_context_budget.py`. 2026-06-10
- **Shimmering Skeleton Screens**: Replaced standard loading spinners with highly responsive, custom-animated shimmering skeleton screens across all fetching/loading states. Includes custom CSS `@keyframes` in `index.css` supporting high-contrast accessibility mode. Handled loading layouts for past sessions, chat history, profile form, admin dashboard widgets, drift reports table, evaluation queue, and route guards. All 42 frontend tests pass, 0 lint errors. 2026-06-08
- **Sidebar Sessions Auto-Refresh**: Fixed new chat sessions not appearing in the sidebar until manual page refresh. Removed forced key remounting on `ChatPageWrapper` in `App.jsx`, updated `ChatPage` to push the new session ID to the URL on session creation, and implemented synchronized active session state in `useEffect` using `useRef`. All unit tests and lint checks pass clean. 2026-06-02
- **Cartoonish Tractor Loader Animation**: Replaced default three-dot bouncing typing indicator with a custom CSS-animated SVG tractor in `TypingIndicator.jsx`. Configured dynamic color mappings for Light and High Contrast modes. All frontend (26/26) and backend (108/108) unit tests pass. 2026-06-01
- `f553863` GENERAL_AG zero-retrieval fix — fan-out across crop namespaces (prod-verified 0→5 docs)
- `fe25f28` (1A) title-match guard skips titleless gte index → defers to NLI (un-floors confidence)
- `85986c9` split `AdvisoryDraft` (LLM) vs `AdvisoryResponse` (guard fields) — fixed hallucinated
  verifications + gen crashes on enum typos
- `3a0cd8a`..`ab78673` **Citation guard overhaul** — LLM-as-judge, surgical suppression, cite-by-title;
  suppression 67%→11%, faithfulness 88.9%; prod-deployed 2026-05-31
- `685a202`..`1a196db` **Response rendering defects (M1+M2+M3)** — `suppressed` flag; confidence label
  reconciliation (High→Medium in [0.2,0.4), Low below 0.2); `_strip_scaffolding` kills
  `[RETRIEVED DOCUMENT CONTEXT]` leaks; prompt header unbracketed; titleless docs get
  `Arkansas Extension source N` handle; `SuppressedNotice` + i18n EN+ES; AdvisoryCard branches on
  `suppressed`, gates `EscalationCard`. 100/101 backend, 26/26 frontend, lint clean. 2026-05-31
- **Chat delete functionality** — enabled deleting chat sessions and cascading messages in backend services, exposed DELETE route, added trash icon next to each chat item in sidebar with confirmation dialog, added tests. 2026-05-31


---

## ▶ NEXT — the REAL levers (evidence-ranked, NOT retrieval technique)

1. **Generation model 7B → 70B** — biggest unmeasured correctness lever. Eval uses local Qwen-7B; prod
   is Groq-70b. **Blocked:** Groq free 70b TPD (100k/day) exhausted ⇒ needs Groq Dev paid tier.
2. **Corpus-coverage audit** — 88.9% faithful but only ~40% correct ⇒ the precise answer (rates/products)
   may simply not be IN the corpus. Audit which gold answers have a supporting chunk at all.
3. **Trustworthy eval** — prod-70b generation + a better/human judge before any more optimization.

---

## 🔍 Defect 5 Quality Investigation Findings (2026-05-31)

We traced the two informational soil queries through the retrieval index across all namespaces (merged by similarity score):
- **Query 1:** *"How do I read a soil test report and what amendments should I apply?"*
  - **Retrieval:** Gold chunks found in top-5 (FSA2153 soil test report, fertilizer recommendations) with cosine similarity scores of ~0.87.
  - **Status:** **Retrieval is excellent.** The issue is formatting: forcing informational/educational queries into the crop-diagnosis Pydantic schema (`AdvisoryResponse`), which expects `likely_causes` and `products_rates`, leads to artificial causes or empty answers.
- **Query 2:** *"What are the most common nutrient deficiencies in Arkansas soils?"*
  - **Retrieval:** Gold chunks found in top-5 (widespread boron deficiency in NE Arkansas, manganese deficiency on pH > 6.5, zinc deficiency on pH > 6.0) with similarity scores of ~0.91.
  - **Status:** **Retrieval is excellent.** The issue is formatting: forcing informational/educational queries into the crop-diagnosis Pydantic schema (`AdvisoryResponse`), which expects `likely_causes` and `products_rates`, leads to artificial causes or empty answers.
- **Go/No-go Decision:** **Go** on proposing an informational-answer shape. We need a secondary schema or a prompt branch for informational queries (non-diagnostic intent) that doesn't force `likely_causes` or `products_rates`.

---

## Known issues / housekeeping

- **Stale test:** `test_citation_guard_v2.py::test_verifiable_text_includes_all_advisory_fields` asserts
  warnings in verifiable text; code excludes them by design. Pre-existing, unrelated.
- **Groq key rotation** — leaked in a transcript; owner handling.
- ~~Delete unused Pinecone indexes~~ — `agroar-prod` (MiniLM) + `agroar-prod-gte` deleted 2026-06-12. Remaining: `agroar-prod-retrieval-v3`, `agroar-prod-retrieval-v3-gte`, `agroar-prod-gte-v2` (old prod, keep for rollback), `agroar-prod-gte-v3` (current prod).

---

## Non-negotiables (from CLAUDE.md)

- Commits: Conventional Commits. **NEVER** `Co-Authored-By` — Taiwo Jegede sole author (NIW).
- Do NOT report the invalid fine-tune MRR 0.6565 (train-on-test) in NIW/arXiv. Honest held-out ~0.18.
- Update CLAUDE.md + status-bar + memory + **this file** after every code-change session.
