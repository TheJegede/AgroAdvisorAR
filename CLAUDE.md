# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Guide Claude Code repo work. (Root `AGENTS.md` = the Codex equivalent of this file; CLAUDE.md is for Claude Code.)

RULE: Always call me my name "Taiwo", at the start of every response.

> **SCOPE OF THIS FILE — read before editing.** CLAUDE.md holds only **stable** repo knowledge: architecture, how to build/test/deploy, conventions, and durable guardrails ("do NOT re-propose X"). It does **NOT** hold volatile status — shipped dates, eval scoreboards, "what's next", per-phase test counts, remediation logs. All of that lives in **`PROGRESS.md`** (the single source of truth for state + dead ends) and project memory. Keeping status out of CLAUDE.md is why it stops going stale — if you're tempted to write "SHIPPED on <date>" or a metric here, put it in PROGRESS.md instead.

## Project
AgroAdvisor AR -> EN/ES RAG advisory for Arkansas farmers. Rice, soybean, poultry. Production + NIW evidence.
**LLM:** Groq-primary (free, no budget): `llama-3.3-70b-versatile` generation, `llama-3.1-8b-instant` classifier/claim-decomp; fallback chain 70b→8b→Gemini `gemini-2.5-flash`. `LLM_PRIMARY` env (`groq`|`gemini`|`local`); `local`=Qwen2.5-7B-4bit on GPU for dev. Transparent to user.
**Stack:** React 19 + Vite + Tailwind SPA. FastAPI backend + SSE RAG. Auth (JWT HS256 via Supabase), profile, history. RAG: ~20k vectors (Pinecone). Rate limit, sanitizer, CORS, Upstash Redis 6h cache.
**Retrieval-eval honesty:** fine-tune v2 reported MRR 0.65 is INVALID (train-on-test); honest 5-fold held-out ~0.18, base 0.12. Do NOT cite 0.65 in NIW/arXiv. See `PROGRESS.md` + eval-contamination memory.
**Docs:** `AgroAdvisor_AR_PRD_v2.md` (spec), `docs/dev-ref.md` (dev ref), `docs/status-bar.md` (progress). `PROGRESS.md` = single source of truth for state + dead ends — **read before planning.** `ERRORS.md` = log of past bugs/CI failures (symptom→cause→fix→prevention); read before debugging recurring CI/test failures and append new ones so they don't repeat.

## Working agreement (durable guardrails)
> Live status, eval numbers, and "what to work on next" are in `PROGRESS.md` "RESUME HERE". The items below are stable rules that don't change session to session.

1. **Read `PROGRESS.md` BEFORE planning.** It records current state and dead ends so you don't re-propose rejected work.
2. **Do NOT re-propose retrieval-technique changes for answer quality.** 5 levers tested + rejected (token-chunking, hybrid BM25, query rewrite, HyDE, ms-marco reranker). Current prod retrieval = 512-char dense Docling-extracted gte index. NOT agentic RAG (10× cost on free tier). Generation is the answer-quality ceiling, not retrieval/guard — see `PROGRESS.md`.
3. **Citation guard root cause is solved, don't reopen it.** A broken NLI judge (not retrieval/generation) was blanking correct grounded answers; fix = LLM-as-judge groundedness (`citation_guard_v2.judge_claims_llm`, `GROUNDEDNESS_JUDGE=llm`) + surgical rate-safe suppression (`_SAFETY_CRITICAL_RE`) + env thresholds (`GUARD_SUPPRESSION_THRESHOLD`/`GUARD_ESCALATION_THRESHOLD`).
4. **Cost discipline.** State paid-token cost and get an OK before eval runs (user is cost-averse; prefer free tiers / spot-checks).

## Commands
**Backend:** `cd backend && uvicorn main:app --reload`. Single test: `pytest tests/test_drift_service.py`.
**Frontend:** `cd frontend && npm run dev`. `npm run build`, `npm run lint`, `npm run test` (vitest). Single test: `npx vitest run src/pages/useSessions.test.js`.
**E2E:** `npx playwright test` (from repo root). Single: `npx playwright test tests/drift-wizard.spec.js`.
**A11y:** `node scripts/a11y-audit.js`.
**Load:** `locust -f backend/tests/locustfile.py`.
**Ingestion:** `cd ingestion && python scraper.py && python pipeline.py [--force]`. Build a new index: `ingestion/embed_corpus.py` (reads pre-extracted `en_chunks/corpus_v3.jsonl`). Zero-cost retrieval spot-check: `cd ingestion && python spot_check.py`.
**Evals:** `cd evals && python eval_runner.py --eval-set eval_set_v2.jsonl`. Full: `EVAL_WRITE_TO_DB=1 RUN_ANSWER_EVAL=1 python eval_runner.py`.
**Diagnostic gate (D3):** `cd <repo> && python -m evals.diagnostic.runner --gold evals/diagnostic/gold_labels.jsonl`. Produces the bucket split (B1/B2/B3/B4/B-MISS/B-ABSENT) with judge-error band. Containment judge = Gemini 2.5-flash (`CONTAINMENT_JUDGE_MODEL`), distinct from the 70B generator.
**Conditional-completeness (L1):** answer-side judge `evals/diagnostic/conditional_judge.py` over `evals/diagnostic/gold_conditional.jsonl` produces `conditional_completeness_rate`. Run via the diagnostic runner; `.env` lives at repo ROOT.

## Conventions
- **Python:** 4-space. Logic in `backend/services/`. Pydantic models in `backend/models/`. Routers thin.
- **JS/JSX:** 2-space. PascalCase components. Hooks `useX.js` co-located in `pages/`. `*.test.js` beside code. Vitest for unit, Playwright for E2E.
- **Commits:** Conventional Commits. NEVER add `Co-Authored-By` trailers — not in commit messages, not in `--trailers`, not via any flag. All commits must show Taiwo Jegede as sole author.
- **Tests:** Mock external APIs (`page.route()` in Playwright). `npm run lint` before handoff.
- **Docs hygiene:** after a session with code changes, update `PROGRESS.md` (state) + project memory. Update CLAUDE.md ONLY when stable facts change (architecture, commands, conventions, guardrails) — never to record status.

## Env
**Backend `.env`:** `GOOGLE_API_KEY`, `PINECONE_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_JWT_SECRET`, `GROQ_API_KEY`. Optional: `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `SENTRY_DSN`, `PINECONE_INDEX_NAME` (EN retrieval index), `EMBEDDING_MODEL_PATH` (e.g. `thenlper/gte-base`), `LLM_PRIMARY` (`groq`|`gemini`|`local`), `ADMIN_USER_IDS` (comma-sep UUIDs), `CORS_ORIGINS`, `RERANK_ENABLED` (default off; `RERANK_MODEL`=`BAAI/bge-reranker-v2-m3`, `RERANK_CANDIDATES`=30 — too heavy for free-tier CPU, enable on GPU/paid host), `GUARD_JUDGE_PROVIDER` (default `gemini` — guard judge chain pinned fast, decoupled from `LLM_PRIMARY`), `GUARD_JUDGE_TIMEOUT_S` (default 8 — per-attempt guard LLM budget before provider fallback). Current live values for index/model live in `PROGRESS.md`, not here.
**Frontend `.env`:** `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.

## Architecture
**Query flow:** `POST /api/v1/query` -> `routers/query.py` -> auth -> rate limit -> `services/sanitizer.py` -> (ES only: `services/translation.translate_to_en`) -> `services/classifier.py` (crop namespace) -> `services/rag.py` (Pinecone top-5; optional `services/reranker.py` rerank over top-30 when `RERANK_ENABLED`; SSURGO+NOAA via `services/context.py`) -> `utils/prompt.py` -> provider chain `with_structured_output(AdvisoryResponse)` (Groq→Gemini, or local) -> citation guard -> (ES only: `translation.translate_advisory_to_es`) -> `services/session.py` (save) -> SSE stream.
**AdvisoryResponse:** `backend/models/advisory.py` — single source of truth for LLM output schema. Citation guard in `rag.py` cross-checks chunk titles; downgrades confidence to Low if no valid citations.
**SSE resilience:** `event_stream()` in `routers/query.py` emits heartbeat keepalives + runs `run_rag_query` as an `asyncio.create_task` and re-raises `CancelledError` (prevents idle-stream reaping / silent-vanish through the Vercel→HF proxy). Progressive stage streaming (Searching→Found N→Writing→Verifying→Advisory) via `asyncio.Queue`; partial-JSON token streaming to a provisional advisory card.
**Frontend API:** `frontend/src/lib/api.js` — axios instance at `/api/v1`, Bearer token from `localStorage`. All hooks use this client. (Blob/PDF downloads must use axios with the Bearer header, not a plain `<a href>` — that carries no token → 401.)
**Frontend state:** `AuthContext` (Supabase session), `LangContext` (en/es toggle), `ThemeContext`. `useSSEQuery.js` drives the streaming chat.
**PWA (Pillar 2):** vite-plugin-pwa (Workbox) precaches the app shell only — `/api/*` is NEVER runtime-cached. Offline = abstention: time-sensitive advisories (rates/spray/dicamba/warnings) render an OfflineSafetyStub (verify + county-agent escalation), never a frozen number; only `isCacheableAsReference` (informational, no rates/warnings/timing) advisories are cached for offline reading, badged "reference only". Logic in `frontend/src/lib/offlineTiering.js` / `offlineSafety.js` / `offlineCache.js` (unit-tested); UI in `OfflineSafetyStub.jsx` + `AdvisoryCard.jsx`. E2E: `frontend/e2e/pwa-offline.spec.js`.
**Admin:** `ADMIN_USER_IDS` env + `is_admin` on profile. `AdminRoute` gates `/admin` and `/admin/queue`. `useDriftReportAdmin` hook for choropleth data.
**Persistence:** Supabase — `chat_sessions`, `chat_messages` (`content_type`: text/advisory/oos, `retrieved_chunks` stored). Drift reports: migration 006.
**Pinecone:** Namespaces by crop (`rice`, `soybeans`, `poultry`). EN retrieval embedder = `EMBEDDING_MODEL_PATH` via `services/embedding.py` (`MiniLMEmbeddings`, model-agnostic). Index is Docling-extracted gte-base (768-dim). Current live index name + vector count + rollback index → `PROGRESS.md` / docling memory.
**Spanish = translate-bridge (replaced F1 dedicated ES RAG):** `query.py` translates an ES query to EN (`services/translation.py`, LLM), runs the all-English pipeline (gte retrieval + EN gen + EN guard), then translates the advisory's user-facing prose back to ES (products/rates/citations preserved). Trigger: UI `req.language=="es"`. `run_rag_query` is English-only (no `detected_lang`). OOS replies localized (`out_of_scope_message`). (Removed: bge-m3 multilingual index, `detect_language`, ES ingestion scripts.)
**LLM provider knowledge:** when working on any LLM-shaped code, consult the `claude-api` skill for current model IDs/pricing/params (latest: Fable 5, Opus/Sonnet/Haiku 4.x) — don't answer from memory.

## F4 Drift Tool (legacy — coexists with the dicamba spray-check)
3-step wizard (`components/drift/DriftReportWizard.jsx`). Open-Meteo auto-fill weather. Reportlab PDF (`services/pdf_generator.py`). AR county choropleth (`components/chat/ARCountyMap.jsx`). Migration 006.

## F4 Dicamba Spray-Check (before-you-spray compliance checklist)
PRD `AgroAdvisor_F4_PRD_v3.md`; phase plans in `docs/superpowers/plans/`. Four gates A/B/C/D. Status (what's shipped/deployed, owner-blocked ops, UNVERIFIED station coords) → `PROGRESS.md` + F4-dicamba memory. Stable architecture:
- **Rules-as-data:** versioned effective-dated `backend/data/dicamba_rules.json` + `services/spray_rules.py` (`resolve_rules` + accessors: `buffers_ft`, `downwind_half_angle_deg`, `soil_moisture_max`). Approved OTT products: `engenia`, `xtendimax`, `tavium`.
- **Gate engine:** `services/spray_check.py` `run_spray_check(...)` runs gates in order A,B,C,D and returns `SprayCheckResponse`. Each check carries a `tier` (`verifiable_fact` | `human_attested`) and bilingual `label`/`reason` (+`_es`). Gate A = legal window; Gate B = field/buffers (`evaluate_gate_b`, station_buffer distance + neighbor/organic attestations); Gate C = live weather (`services/weather_now.py` Open-Meteo + inversion risk + `soil_not_saturated`; inversion never auto-passes); Gate D = downwind-cone geometry (`evaluate_gate_d`, `spray_stations.bearing_deg`/`angular_diff`) + 5 equipment attestations.
- **Stations:** `services/spray_stations.py` (`load_stations`/`haversine_ft`/`nearest_station`/`bearing_deg`), `backend/data/ar_research_stations.json` (single-sourced — gate engine + `GET /dicamba/stations` both read `load_stations()`).
- **Records:** immutable append-only `spray_records` table (migration `009`, RLS owner SELECT+INSERT, no UPDATE/DELETE) + `services/spray_record.py` (`farmer_id` from JWT = anti-IDOR) + `pdf_generator.generate_spray_record_pdf`. Feedback loop: `services/spray_feedback.py` + migration `010`.
- **Endpoints (`routers/dicamba.py`):** `POST /dicamba/check`, `POST /dicamba/record` (re-runs check server-side, persists frozen snapshot), `GET /dicamba/records`, `GET /dicamba/record/{id}`, `GET /dicamba/record/{id}/pdf`, `GET /dicamba/stations`, `GET /dicamba/stats` (admin), `POST /dicamba/feedback`. Models in `models/spray.py`.
- **Frontend:** `components/dicamba/SprayCheckWizard.jsx` (4 steps: Eligibility A → Field & Buffers B → Live Conditions C → Confirm & Result; react-leaflet click-to-place pin + buffer `Circle`s + station `CircleMarker`s) + `hooks/useSprayCheck.js` + `pages/SprayCheckPage.jsx` (`/spray-check`); `useSprayRecords` + `SprayRecordsPage` (`/spray-records`). EN+ES, HC badges, `min-h-touch`. Bilingual disclaimer constants above every step. Deps: `react-leaflet`, `leaflet`.

## Deploy
**Frontend (Vercel):** `git push origin main` auto-deploys. Project `agroadvisor`, GitHub-connected (repo `TheJegede/AgroAdvisorAR`, branch `main`, **Root Directory=`frontend`** — must stay set or builds fail `vite: command not found`). `.npmrc` (`legacy-peer-deps=true`) required for React 19 + react-simple-maps@3. CLI fallback: `vercel --prod --cwd frontend`. Same-origin via `frontend/vercel.json` `/api/*` rewrite (no CORS).
**Backend (HF Spaces, Docker, 2 CPU/16GB — Koyeb/Render 512MB too small for torch+gte+guard ~1.5-2GB):** auto-redeploys via GitHub Action `.github/workflows/deploy-backend.yml` on every push to `main` touching `backend/**`/`Dockerfile`/`.dockerignore`/`README-space.md` (orphan-push replica using repo secret `HF_TOKEN`, write scope on `WhoIsLuwah/agroadvisor-backend`). Also `workflow_dispatch`. Manual fallback if the Action is down: `git checkout --orphan hf-deploy && git reset && cp README-space.md README.md && git add backend Dockerfile .dockerignore README.md && git commit -m deploy && git push space hf-deploy:main --force && git checkout -f main` (orphan required — HF rejects the binary files in full repo history).
