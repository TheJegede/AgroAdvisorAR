# PROGRESS.md — AgroAdvisor AR

> **Single source of truth for "where are we / what's been tried."** Read this BEFORE
> writing any plan so we don't re-propose dead ends. Update it after every session
> with code changes (alongside CLAUDE.md + status-bar + memory).
>
> **Last updated:** 2026-06-08 (F4 dicamba rebuild — Phases 0-5 shipped: rules-as-data, /check Gates A-D, wizard, Gate B map, record/Gate D, Spanish parity + soil + registry deep-links)
> Companion docs: `CLAUDE.md` (Priorities), `docs/status-bar.md` (% rollup),
> `~/.claude/.../memory/project_eval_contamination.md` (why the retrieval metric lies).

---

## ⏸ DEFERRED OPS — tend AFTER Phase 6 (owner decision 2026-06-08)

These are intentionally parked, NOT forgotten. Do not action until Phases 5 + 6 land.

1. **Apply migration `009_spray_records.sql` to prod Supabase** — the `spray_records` table + RLS
   only exist in the repo; prod has no table yet, so `POST /dicamba/record` will 500 in prod until
   applied. (Local/test fine — tests mock the client.)
2. **HF backend orphan-branch redeploy** — accumulated debt for Phases 1→4. The live HF Space still
   serves the pre-F4 backend, so `/dicamba/check` (4 gates), `/dicamba/stations`, and all
   `/dicamba/record*` endpoints are NOT live in prod. Redeploy procedure: CLAUDE.md Priorities §2.
   Frontend (Vercel) auto-deploys on push, so the wizard is live but calls endpoints that 404 in prod
   until this redeploy.
3. **Research-station coordinates UNVERIFIED** — `backend/data/ar_research_stations.json` ships with a
   top-level `source` marked UNVERIFIED; validate the 10 UA/USDA-ARS coords against an authoritative
   source before any pilot reliance (Gate B + Gate D both depend on them).
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
  prod debt as Phase 4. **NEXT = Phase 6** (legal review + pilot).
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
| Index | `agroar-prod-gte-v2` | gte-base 768-dim, ~20,546 vectors, includes titles & sections |
| Chunking | **512 CHARACTERS** (`ingestion/chunker.py`, `length_function=len`) | NOT tokens (token-chunking regressed — see rejected table) |
| Retrieval | dense-only, top-5 | |
| Reranker | **OFF** | |
| Embedder | `thenlper/gte-base` | `EMBEDDING_MODEL_PATH` env |
| Generation | Groq `llama-3.3-70b` / DeepInfra Llama 3.3 70B (prod) | |
| Groundedness judge | LLM-as-judge (`GROUNDEDNESS_JUDGE=llm`) | NLI offline fallback only |

Run prod-config eval:
`EMBEDDING_MODEL_PATH=thenlper/gte-base PINECONE_INDEX_NAME=agroar-prod-gte-v2 python evals/{eval_runner,answer_eval}.py`

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
- Delete unused Pinecone indexes when sure: `agroar-prod-multilingual`, legacy `agroar-prod` (MiniLM).

---

## Non-negotiables (from CLAUDE.md)

- Commits: Conventional Commits. **NEVER** `Co-Authored-By` — Taiwo Jegede sole author (NIW).
- Do NOT report the invalid fine-tune MRR 0.6565 (train-on-test) in NIW/arXiv. Honest held-out ~0.18.
- Update CLAUDE.md + status-bar + memory + **this file** after every code-change session.
