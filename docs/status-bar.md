# AgroAdvisor AR — Completion to Production

**Last updated:** 2026-06-08  
**MVP target:** September 2026  
**Production readiness:** 82%  
**PRD phase progress:** 80%

```
Production readiness  [████████████████░░░░]  82%
PRD phase progress    [████████████████░░░░]  80%
```

**LIVE + SMOKE-TESTED (2026-05-30):** frontend `https://agroadvisor-eta.vercel.app`
(Vercel) → API proxy → backend `https://whoisluwah-agroadvisor-backend.hf.space`
(HF Spaces). Verified in-browser: register/login, county/soil/weather context,
persistence, an EN rice query returns a grounded cited advisory (`agroar-prod-gte`
confirmed populated), and the **Spanish translate-bridge round-trips** (ES query →
EN RAG → ES answer; ES and EN give identical behaviour = bridge is transparent).
`FRONTEND_URL` set + prod migrations 005/007/008 run.

**CI/CD (2026-05-30):** frontend auto-deploys on `git push origin main` — Vercel
project `agroadvisor` is GitHub-connected (Root Directory=`frontend`). Backend
redeploys via orphan-branch force-push to the HF git remote. Accidental duplicate
Vercel projects (`agro-advisor-ar*`) cleaned up. Exact redeploy commands: CLAUDE.md
Priorities #2.

🚧 **F4 DICAMBA REBUILD (PRD v3) — IN PROGRESS (Phases 0 + 1 shipped 2026-06-08).** F4 reframed
from a backward-looking drift-complaint form into a *before-you-spray dicamba compliance checklist*
(four gates A legal-window / B field-buffers / C weather-now / D equipment; `AgroAdvisor_F4_PRD_v3.md`).
**Coexists** with the old drift tool (T1) — does not replace it. New scope, tracked separately from the
MVP-blocker % below. 7-phase plan in `docs/superpowers/plans/2026-06-08-f4-dicamba-phase{0..6}-*.md`.

```
F4 dicamba rebuild (7 phases)  [█████░░░░░░░░░░░░░░░░]  29%  (2/7 phases shipped)
```

| Phase | Scope | Done? |
|---|---|---|
| 0 | Versioned rules-as-data (`dicamba_rules.json` + `spray_rules.py`) | ☑ 2026-06-08 (merged `dcdc12b`) |
| 1 | `POST /api/v1/dicamba/check` — Gates A + C (forecast weather + gate engine) | ☑ 2026-06-08 (merged `c86b966`) |
| 2 | SprayCheckWizard UI + react-leaflet field pin, wired to `/check` | ☐ next |
| 3 | Gate B field & buffer proximity map | ☐ |
| 4 | Record generator (`/record`, `spray_records` table, Gate D, PDF) | ☐ |
| 5 | External data (FieldWatch / EPA Bulletins) + full Spanish parity | ☐ |
| 6 | Attorney review of advisory framing + pilot | ☐ |

> Backend endpoint is on `main` but **not yet HF-redeployed** (manual orphan-branch push); fine — the
> frontend doesn't call `/check` until Phase 2.

✅ **CITATION GUARD OVERHAUL SHIPPED + merged to `main` 2026-05-31 (Phases 1–6).** The broken
MiniLM NLI judge is retired; an LLM-as-judge (provider chain) scores groundedness, suppression
is surgical + rate-safe, and `Document N:` is killed at the prompt source. Effect (local-Qwen gen
+ Gemini judge, gte, n=9): **suppression 67%→11%, faithfulness 88.9%, confidence_score 0.64–1.00
mean**. Backend redeployed to HF.

✅ **INFORMATIONAL ROUTING (DEFECT 5) SHIPPED + fully tested 2026-05-31.** Added branched prompt instructions and Pydantic models for educational queries (avoiding diagnostic schemas), updated the classifier, and branched card rendering in the UI. Checked against local unit tests and Vitest (0 failures).

✅ **FIXED + shipped 2026-05-30 (`f553863`): GENERAL_AG zero-retrieval bug.**
`IN_SCOPE_GENERAL_AG` mapped to `None`, which made Pinecone search the empty
default namespace → 0 docs → NLI 0.00 → every general-ag answer suppressed (all
20k vectors live in rice/soybeans/poultry; no `general` namespace). Fix:
`rag._namespaces_for` + `_fanout_search` fan out across the crop namespaces, merge
by score. TDD'd (`tests/test_rag_retrieval.py`); live proof 0→5 docs; verified in
prod (cover-crop query: NLI 0.00 → 0.34, suppressed → populated).

✅ **RETRIEVAL MECHANICS EXHAUSTED 2026-05-30 — 5 levers tested, ALL rejected; deployed
config wins (40% corr / 82.5% faith).** Token-chunking (regression, REVERTED `f07b523`),
hybrid BM25 (flat), query rewrite (wash), HyDE (worse), ms-marco reranker (regression).
Real next levers are NOT retrieval technique → see PROGRESS.md. Two confounds make absolute
numbers unreliable (single-gold metric + local-Qwen eval vs prod Groq-70b).

✅ **GT INDEX WITH METADATA SWITCHED 2026-06-03.** Switched active Pinecone index from `agroar-prod-gte` (which lacked document titles) to `agroar-prod-gte-v2` (contains all `document_title` and `section_heading` metadata). Validated that retrieval metrics are maintained (`MRR@5` `0.1508` -> `0.1533`) and the title-matching citation guard now successfully validates citations end-to-end.

✅ **CODE REVIEW REMEDIATION SHIPPED + merged to `main` + deployed 2026-06-06.** All 15 findings + honorable mentions from `docs/2026-06-05-codebase-logic-review.md` fixed (TDD, 1 commit/finding). Security/correctness highlights: **IDOR write** in `session.add_message` closed (ownership check); safety-guard **bare-`\d` over-match** that wiped grounded answers fixed; rate limiter no longer **fails open** on Redis outage (local fallback); SAFETY_CRITICAL gets explicit fan-out + escalation; SSE error frame no longer **leaks raw exceptions**; JWT alg allowlist pinned. Verified backend 131 / frontend 29 / lint clean. Merged to `main`, pushed, frontend auto-deployed (Vercel), backend redeployed to HF Spaces.

Still open (next levers, evidence-ranked):
- **Generation model 7B → 70B** — Completed (2026-06-03). Integrated DeepInfra 70B (Llama 3.3) to bypass Groq rate/billing tier blocks.
- **Corpus-coverage audit** — Completed (2026-06-03). Verified 100% of gold queries have supporting chunks in the corpus.
- **Trustworthy eval** — ✅ Done (2026-06-05). DeepInfra 70B gen + judge, n=20, seed=7: correctness **20%**, faithfulness **40%**, suppression **15%**. Poultry leads (50% corr), soybeans lags (43% suppressed). See PROGRESS.md eval section.
- **Namespace audit + relabeled eval** — ✅ Done (2026-06-06). LLM audit relabeled 40/70 soybeans items to `general` (off-crop content: pine, wheat, Clearfield rice, sprayer calibration). Relabeled eval n=41, seed=7: correctness **22%**, faithfulness **49%**, suppression **10%**. Soybeans post-relabel: corr 25%, faith 50%, supp 0% (genuine queries only). Canonical eval for arXiv/NIW: `evals/eval_set_v2_relabeled.jsonl`.


---

## PRD Phase Rollup

```
Phase 1 — Foundation        [███████████████████░]  95%
Phase 2 — RAG               [███████████████████░]  95%
Phase 3 — Frontend          [████████████████████]  99%
Phase 4 — Test/Pilot/NIW    [██████░░░░░░░░░░░░░░]  30%
```

PRD phase progress is the average of the current phase percentages from `docs/prd-progress-audit-2026-05-16.md`: `(95 + 95 + 98 + 30) / 4 = 79.5%`, rounded to 80%.

---

## By Dimension

```
Core RAG system        [███████████████████░]  93%
Frontend UI            [███████████████████░]  98%
Security / testing     [████████████████░░░░]  80%
Deployment (prod URL)  [███████████████████░]  95%
Real users / data      [░░░░░░░░░░░░░░░░░░░░]   0%
NIW evidence package   [█░░░░░░░░░░░░░░░░░░░]   5%
```

---

## Remaining Blockers

| # | Item | Dimension affected | Delta | Done? |
|---|---|---|---|---|
| 1 | Deploy to Vercel + Hugging Face Spaces (prod URL live) | Deployment | +7% | ☑ (2026-05-30; URL live + API proxy verified) |
| 2 | OWASP Top 10 review + Playwright E2E suite | Security/testing | +5% | ☑ |
| 3 | 20 pilot farmers recruited + 500 real queries | Real users / data | +12% | ☐ |
| 4 | arXiv preprint submitted | NIW evidence | +6% | ☐ |
| 5 | UA Extension agent scoring in eval queue | NIW evidence | +7% | ☐ |
| 6 | Add `GROQ_API_KEY` to GH secrets (answer_correct_pct CI) | Security/testing | +1% | ☑ |
| 7 | Full WCAG audit on auth-gated routes (Playwright + axe) | Security/testing | +1% | ☑ |
| 8 | Public GitHub README (arch diagram + eval results) | NIW evidence | +2% | ☑ (2026-06-03; restored and fully updated) |
| 9 | Locust load test (50 concurrent users) | Security/testing | +1% | ☐ |
| **Tier 1 Features (planned — Tier1_Implementation_Plan Addition.md)** | | | | |
| T1 | F4 · Dicamba drift tool deployed (wizard + PDF, prod URL live) | Real users / data | +3% | ☑ (deployed + live 2026-05-30) |
| T2 | F3 · First RWW/Palmer alert fired to pilot farmer | Real users / data | +3% | ☐ (deployed 2026-05-30; pending pilot alert) |
| T3 | F2 · Citation guard v2 live (confidence scores in prod) | Security / testing | +2% | ☑ (live + smoke-tested 2026-05-30; NLI scores render in prod) |
| T4 | F5 · AWD scheduler live + first re-flood alert fired | Core RAG system | +2% | ☐ (deployed 2026-05-30; pending pilot alert) |
| T5 | Spanish translate-bridge live (ES query → EN RAG → ES answer) | Core RAG system | +3% | ☑ (smoke-tested in prod 2026-05-30; ES round-trips, behaviour ≡ EN) |
| T6 | F1 · arXiv preprint submitted with F1+F2 contributions | NIW evidence | +6% | ☐ |

**Check off items above → update bars + production-readiness % → update PRD phase rollup when `docs/prd-progress-audit-2026-05-16.md` changes → update "Last updated" date.**

---

## Completed (contributed to current 80%)

| Item | Dimension | Completed |
|---|---|---|
| OWASP Top 10 audit (1 critical fixed: A07 login rate limit) | Security/testing | 2026-05-16 |
| Playwright E2E suite (15 tests across 7 spec files + CI workflow) | Security/testing | 2026-05-16 |
| Locust load test file written (local + prod run commands ready) | Security/testing | 2026-05-16 |
| `GROQ_API_KEY` added to GH secrets — nightly answer-eval CI now fully operational | Security/testing | 2026-05-17 |
| Playwright CI stabilized — helpers.js, selector fixes, JSON parse fix, vite proxy config; CI workflow updated | Security/testing | 2026-05-17 |
| SQL migration 004 made idempotent (DROP POLICY IF EXISTS before CREATE POLICY) | Core RAG | 2026-05-17 |
| Full WCAG 2.1 AA audit on 4 auth-gated routes (0 violations: /, /profile, /admin, /admin/queue) | Security/testing | 2026-05-16 |
| Supabase schema + RLS (all 6 tables) | Core RAG | 2026-05-16 |
| Pinecone index (384-dim, 20,546 vectors) | Core RAG | 2026-05-16 |
| UA Extension scraper + 200+ PDFs ingested | Core RAG | 2026-05-16 |
| Auth endpoints + JWT (ES256 JWKS + HS256) | Core RAG | 2026-05-16 |
| SSURGO + NOAA context injection (6h Redis cache) | Core RAG | 2026-05-16 |
| RAG chain (k=5, namespace filter, citation guard) | Core RAG | 2026-05-16 |
| Query classifier (Groq 8b-instant primary; Gemini fallback) | Core RAG | 2026-05-16 |
| EN retrieval: gte-base index `agroar-prod-gte` + optional reranker (MRR 0.6565 was train-on-test/INVALID; honest held-out ~0.18; gte+reranker relevance-judged ~0.6) | Core RAG | 2026-05-29 |
| Nightly eval CI + `eval_runs` table | Core RAG | 2026-05-16 |
| LLM-as-judge answer eval | Core RAG | 2026-05-16 |
| Rate limit 20q/hr (Redis) + prompt injection sanitizer | Security/testing | 2026-05-16 |
| JWT audience enforcement (`aud: "authenticated"`) | Security/testing | 2026-05-16 |
| CORS locked to `CORS_ORIGINS` env var | Security/testing | 2026-05-16 |
| Backend unit tests (5 pytest) + frontend (3 vitest) | Security/testing | 2026-05-16 |
| React 19 + Vite + Tailwind frontend | Frontend UI | 2026-05-16 |
| Multi-step register wizard (3-step, EN+ES) | Frontend UI | 2026-05-16 |
| Login + forgot/reset password flow | Frontend UI | 2026-05-16 |
| Sidebar + chat pane (mobile responsive) | Frontend UI | 2026-05-16 |
| Structured response accordion renderer | Frontend UI | 2026-05-16 |
| SSE consumer | Frontend UI | 2026-05-16 |
| High-contrast mode (HC toggle, localStorage persist) | Frontend UI | 2026-05-16 |
| WCAG fixes on /login + /register (axe-core 0 violations) | Frontend UI | 2026-05-16 |
| Feedback widget + `/feedback` endpoint | Frontend UI | 2026-05-16 |
| Admin dashboard + human eval queue + scoring UI | Frontend UI | 2026-05-16 |
| AR county choropleth (react-simple-maps) | Frontend UI | 2026-05-16 |
| Session persistence + conversation history | Frontend UI | 2026-05-16 |
| Google OAuth via Supabase (`Continue with Google` live — `supabase.js`, `AuthCallbackPage.jsx`, profile-completion gate) | Frontend UI | 2026-05-19 |
| Auth page glassmorphism parity (Register/Forgot/Reset now match Login style; white wrapper removed from RegisterPage) | Frontend UI | 2026-05-19 |
| i18n cleanup — 5 hardcoded LoginForm strings moved to `i18n.js` EN+ES (`enterApp`, `rememberMe`, `quickAccessVia`, `continueWithGoogle`, `createAccount`) | Frontend UI | 2026-05-19 |
| `isNewChat` lint fix — `npm run lint` now passes 0 errors | Frontend UI | 2026-05-19 |
| F4 Dicamba drift tool — wizard (3-step, EN+ES), Open-Meteo weather auto-fill, reportlab PDF, migration 006, admin drift tab + amber choropleth layer, 3 Playwright E2E tests | Frontend UI + Core RAG | 2026-05-20 |
| F3 alerts code — GDD calculator, alert engine, alert rules, migration 005, nightly alert workflow, frontend alert banner | Core RAG + Real users/data | 2026-05-28 |
| F2 citation guard v2 code — claim-level NLI service, confidence-score fields, escalation UI, migration 008 | Security/testing | 2026-05-28 |
| F5 AWD scheduler code — AWD scheduler, USGS well context, rice fields migration 007, AWD alert integration | Core RAG | 2026-05-28 |
| Spanish translate-bridge — `services/translation.py` (ES→EN query, EN→ES answer); replaced the F1 dedicated ES RAG (BGE-M3 index/routing/ingestion all removed) | Core RAG | 2026-05-29 |
| **Production deploy** — backend Docker on HF Spaces (`whoisluwah-agroadvisor-backend.hf.space`, 2 CPU/16GB), frontend on Vercel (`agroadvisor-eta.vercel.app`), wired via Vercel `/api/*` rewrite proxy (same-origin, no CORS). Dockerfile + `.dockerignore` + `frontend/vercel.json` + `.npmrc` (legacy-peer-deps). API proxy verified (FastAPI 401 answers through it). | Deployment | 2026-05-30 |
| **Prod smoke test passed** — in-browser: register/login, EN rice query → grounded cited advisory (`agroar-prod-gte` populated), county/soil/weather context, persistence, Spanish translate-bridge round-trip (ES ≡ EN). `FRONTEND_URL` + prod migrations 005/007/008 applied. | Deployment | 2026-05-30 |
| Chat welcome chips re-localize on language toggle — `ChatPage.jsx` `useMemo` dep fixed from `[]` → `[lang]` (chips were frozen to mount-time language) | Frontend UI | 2026-05-30 |
| Retrieval-mechanics research arc — 5 levers tested + rejected (token-chunk reverted `f07b523`, hybrid BM25, query rewrite, HyDE, ms-marco reranker); deployed config wins (40% corr/82.5% faith); reusable free local-Qwen A/B eval tooling left in tree | Core RAG | 2026-05-30 |
| Citation guard overhaul — LLM-as-judge replaces broken NLI, surgical rate-safe suppression, cite-by-title; suppression 67%→11%, faith 88.9%; merged to main + HF redeployed (`3a0cd8a`..`ab78673`) | Core RAG | 2026-05-31 |
| Informational routing (Defect 5) — branched prompt/intent classification, updated advisory model, gated front-end rendering, added backend tests | Core RAG | 2026-05-31 |
| Chat delete functionality — enabled deleting chat sessions and cascading messages in backend services, exposed DELETE route, added trash icon next to each chat item in sidebar with confirmation dialog, added tests | Frontend UI + Core RAG | 2026-05-31 |
| Cartoonish Tractor Loader Animation — replaced default TypingIndicator with custom CSS-animated SVG tractor driving past crops, fully responsive and styled for High Contrast mode, tests pass | Frontend UI | 2026-06-01 |
| Sidebar Sessions Auto-Refresh — fixed new chat sessions not appearing in sidebar until manual page refresh by refactoring activeSessionId sync in useEffect and pushing session ID to URL | Frontend UI | 2026-06-02 |
| DeepInfra 70B Integration & Gemini Fallback Upgrades — added DeepInfra Llama 3.3 70B as primary/fallback provider using Pydantic JSON mode parsing and reverted deprecated Gemini models to active gemini-2.5-flash series | Core RAG | 2026-06-03 |
| Pinecone v2 Index Metadata Cutover & Citation Guard Calibration — cut over to agroar-prod-gte-v2 index (complete with titles/sections), calibrated safety-critical regex to ignore growth stages (V3/R5/V3.5), verified 109 backend tests pass | Core RAG | 2026-06-03 |
| Code review remediation — all 15 findings + honorable mentions from the 2026-06-05 logic review fixed (IDOR write, safety-guard over-match, rate-limit fail-open, SAFETY_CRITICAL routing, GDD cap, alert dedup, SSE error leak, NFKC length cap, weather noon/wind, JWT alg pin, +more); merged to main + deployed (backend 131 / frontend 29 tests pass) | Security/testing + Core RAG | 2026-06-06 |
| F4 dicamba rebuild Phase 0 (PRD v3) — versioned effective-dated rules-as-data `backend/data/dicamba_rules.json` + `services/spray_rules.py` (`resolve_rules` by date + accessors); 10 TDD tests; merged to main (`dcdc12b`) | Core RAG | 2026-06-08 |
| F4 dicamba rebuild Phase 1 (PRD v3) — `POST /api/v1/dicamba/check` Gates A (legal window) + C (weather now); new Open-Meteo **forecast** client `services/weather_now.py` (+ inversion-risk estimate that never auto-passes), gate engine `services/spray_check.py` (verifiable_fact vs human_attested), `models/spray.py`, `routers/dicamba.py`; 25 TDD tests, full backend 166 pass; merged to main (`c86b966`) | Core RAG | 2026-06-08 |



---

## How to Update

1. Complete a blocker item above
2. Check its box ☑
3. Add it to the Completed table with date
4. Recalculate production-readiness % (current 70% + item delta)
5. Recount filled blocks: `round(pct / 5)` blocks out of 20
6. Update "Last updated" date
7. Update relevant dimension bar
8. If a PRD phase percentage changed in the audit, update `PRD phase progress`

**Block scale:** each `█` = 5%. e.g. 70% = 14 filled blocks → `[██████████████░░░░░░]`
