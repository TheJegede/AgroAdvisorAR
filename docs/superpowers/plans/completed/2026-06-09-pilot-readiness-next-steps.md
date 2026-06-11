# Pilot-Readiness — Next Steps (kickoff plan)

> **Status at write (2026-06-09):** Pillar 0 (diagnostic harness) + Pillar 2 (PWA channel) CODE SHIPPED, merged to `main` (`a35ae47`), pushed to origin. PWA auto-deployed to Vercel prod. This plan = what to do NEXT session. Source PRD: `AgroAdvisor_pilot_readiness_PRD.md` (local). Companion: `docs/superpowers/plans/2026-06-09-diagnostic-harness.md`, `2026-06-09-pwa-channel.md` (local). Tests green: 33 pytest / 71 vitest / 2 playwright.

**Goal:** Turn the shipped diagnostic harness into an actual D3 bucket split (the gate), then build only the answer-quality lever the split earns. Plus close the small PWA prod-verify + doc loose ends.

**Critical path:** gold-labeling → run diagnostic → read split → build earned lever. Levers (L1/L2/L3/ingestion) were deliberately deferred and MUST stay deferred until the split exists.

---

## Track A — Gold-label candidate scaffolding (unblocks the gate)

The gate's input is a human-produced `evals/diagnostic/gold_labels.jsonl` (~30–40 items). Schema is pinned by `evals/diagnostic/gold_schema.py` (`GoldRecord`). The labeling itself is human work (transcribe-don't-invent), but most of the grind can be machine-scaffolded so the human only transcribes gold answers + assigns buckets.

**A1 — Surface the real failing queries.**
- Run the existing answer eval to get actual failures (not guesses):
  `cd evals && RUN_ANSWER_EVAL=1 python eval_runner.py` (or `answer_eval.py` / `answer_eval_full.py` — confirm which writes per-item results to `evals/results/`).
- A "failure" candidate = correctness-fail or suppressed item from the n=20 70B prod eval baseline (correctness 20% / faithfulness 40% / suppression 15% — see PROGRESS.md "70B Prod Eval Results").

**A2 — Write a scaffolder script** `evals/diagnostic/scaffold_gold.py` (NEW):
- Input: the eval results / failing queries.
- For each failing query emit a partial gold record with `query`, `namespace` filled, and `source_in_index` pre-populated by calling `evals.diagnostic.source_index.doc_title_in_index(...)` against the live Pinecone index (the helper already exists + is tested with injected fakes; here use the real `_default_index_and_embed()`).
- Leave `gold_found`, `gold_answer`, `gold_source`, `gold_snippet`, `rule_type`, `human_bucket`, `set_aside` blank/null for the human.
- Output `evals/diagnostic/gold_labels.candidate.jsonl`.
- TDD: unit-test the pure record-shaping (`build_candidate_record(query, namespace, source_in_index) -> dict`) with a fake index; do NOT hit Pinecone in tests.

**A3 — Human pass (manual, NOT a coding task):** transcribe gold answers from the corpus into `gold_labels.jsonl`, tag `rule_type` (conditional|flat) + `human_bucket` on a ~10-item calibration slice, `set_aside` the hard cases (no Extension expert). Transcribe-don't-invent: every `gold_found:true` needs a verbatim `gold_snippet`.

---

## Track B — Run the gate, read the split

**B1 — Run:** `python -m evals.diagnostic.runner --gold evals/diagnostic/gold_labels.jsonl`
- Needs `GOOGLE_API_KEY` (Gemini judge) + Pinecone/backend env in `.env`. Runs the live RAG per item.
**B2 — Read the report:** bucket counts + `judge_error_rate` (disagreement vs human calibration slice) + `lever1_conditional_fraction_of_b2`.
**B3 — Sanity gate:** if `judge_error_rate` is high (judge unreliable), fix calibration before trusting the split. If `B_ABSENT_answered > 0` → hallucination flag (pipeline answered something not in source of truth) — investigate first, it's a safety signal.

---

## Track C — Build the lever the split earns (GATED on Track B)

Decision tree (do NOT pre-commit; decide from the split):
- **B2-heavy (answerable, generation failed):** prompt / schema work. Note the informational-vs-diagnostic schema finding already in PROGRESS.md (forcing informational queries into the crop-diagnosis Pydantic schema → empty/artificial answers; "Go" on an informational-answer shape). `lever1_conditional_fraction_of_b2` tells whether conditional-rule handling (L1) is the substrate.
- **B3-heavy (true corpus gap):** ingestion — fill the missing docs (esp. soybeans, which showed 43% suppression). `ingestion/scraper.py` + `pipeline.py`.
- **B-MISS-heavy (in index, not retrieved):** retrieval — but note 5 retrieval levers already tested+rejected (PROGRESS.md table); be skeptical, this should be rare.
- **B1/B-ABSENT (correct abstention):** no work — that's the system behaving.

Write a per-lever TDD plan into `docs/superpowers/plans/` ONLY after the split names the lever.

---

## Track D — PWA + doc loose ends (small, ungated)

**D1 — Prod verify:** PWA is live on Vercel (auto-deployed on the push). On a phone: confirm installable (add-to-home-screen), then airplane-mode → a time-sensitive advisory shows the OfflineSafetyStub (verify + county agent), NOT a frozen rate; a reference advisory shows with "reference only" badge.
**D2 — Lighthouse:** `cd frontend && npm run build && npm run preview` → Chrome devtools Lighthouse Mobile → PWA + Performance pass; no horizontal scroll at 360px; tap targets ≥44px.
**D3 — PRD M5 wording:** edit `AgroAdvisor_pilot_readiness_PRD.md` M5 from "last-N answers readable offline" → "last-N *reference* answers readable offline; time-sensitive answers show the verify stub." (local/gitignored file.)

---

## Notes for the cold-start session
- Diagnostic package: `evals/diagnostic/` (gold_schema, span_verify, pipeline_flags, buckets, containment_judge, source_index, runner) — all unit-tested, run `python -m pytest evals/tests/test_diagnostic_*.py -v`.
- PWA helpers: `frontend/src/lib/offline{Tiering,Cache,Safety}.js` + hooks + `OfflineSafetyStub`.
- Containment judge = Gemini 2.5-flash (`CONTAINMENT_JUDGE_MODEL`), deliberately a different model from the DeepInfra/Groq 70B generator — do not "simplify" to one model.
- Memory: `[[project-pilot-readiness]]`, `[[project-answer-quality]]`, `[[project-guard-root-cause]]`, `[[project-eval-contamination]]` (why retrieval MRR lies — do not report 0.6565).
- These plan files + the PRD are LOCAL/gitignored by design; they're referenced from PROGRESS.md + CLAUDE.md.
