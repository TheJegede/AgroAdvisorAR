# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Guide Claude Code repo work.

## Project
AgroAdvisor AR -> EN/ES RAG advisory Arkansas farmers. Rice, soybean, poultry. Production + NIW evidence.
**LLM:** Gemini `gemini-2.5-flash` primary; `gemini-2.5-flash-lite` classifier; Groq `llama-3.3-70b-versatile` fallback on 429. Transparent to user.
**Stack:** React 19 + Vite + Tailwind SPA. FastAPI backend + SSE RAG. Auth (JWT HS256 via Supabase), profile, history. RAG: 20k vectors (Pinecone), fine-tune v2 (MRR 0.65). Rate limit, sanitizer, CORS, Upstash Redis 6h cache.
**Docs:** `AgroAdvisor_AR_PRD_v2.md` (spec), `docs/dev-ref.md` (dev ref), `docs/status-bar.md` (progress).

## Priorities
1. **Tier 1:** F4(done) -> F3(alerts) -> F2(citations) -> F5(AWD) -> F1(ES RAG).
2. **Deploy:** Vercel (frontend) + Koyeb (backend). Set ENV vars.
3. **Pilot:** 20 users, 500 queries.
4. **Polish:** `farm-bg.png` -> webp.

## Commands
**Backend:** `cd backend && uvicorn main:app --reload`. Single test: `pytest tests/test_drift_service.py`.
**Frontend:** `cd frontend && npm run dev`. `npm run build`, `npm run lint`, `npm run test` (vitest). Single test: `npx vitest run src/pages/useSessions.test.js`.
**E2E:** `npx playwright test` (from repo root). Single: `npx playwright test tests/drift-wizard.spec.js`.
**A11y:** `node scripts/a11y-audit.js`.
**Load:** `locust -f backend/tests/locustfile.py`.
**Ingestion:** `cd ingestion && python scraper.py && python pipeline.py [--force]`.
**Evals:** `cd evals && python eval_runner.py --eval-set eval_set_v2.jsonl`. Full: `EVAL_WRITE_TO_DB=1 RUN_ANSWER_EVAL=1 python eval_runner.py`.

## Conventions
- **Python:** 4-space. Logic in `backend/services/`. Pydantic models in `backend/models/`. Routers thin.
- **JS/JSX:** 2-space. PascalCase components. Hooks `useX.js` co-located in `pages/`. `*.test.js` beside code. Vitest for unit, Playwright for E2E.
- **Commits:** Conventional Commits. NEVER add `Co-Authored-By` trailers — not in commit messages, not in `--trailers`, not via any flag. All commits must show Taiwo Jegede as sole author.
- **Tests:** Mock external APIs (`page.route()` in Playwright). `npm run lint` before handoff.

## Env
**Backend `.env`:** `GOOGLE_API_KEY`, `PINECONE_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_JWT_SECRET`, `GROQ_API_KEY`. Optional: `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `SENTRY_DSN`, `PINECONE_INDEX_NAME` (default: `agroar-prod`), `ADMIN_USER_IDS` (comma-sep UUIDs), `CORS_ORIGINS`.
**Frontend `.env`:** `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.

## Architecture
**Query flow:** `POST /api/v1/query` -> `routers/query.py` -> auth check -> rate limit -> `services/sanitizer.py` -> `services/classifier.py` (crop namespace) -> `services/rag.py` (Pinecone top-5, SSURGO+NOAA via `services/context.py`) -> `utils/prompt.py` (build system prompt) -> Gemini `with_structured_output(AdvisoryResponse)` -> citation guard -> `services/session.py` (save) -> SSE stream.
**AdvisoryResponse:** `backend/models/advisory.py` — single source of truth for LLM output schema. Citation guard in `rag.py` cross-checks chunk titles; downgrades confidence to Low if no valid citations.
**Frontend API:** `frontend/src/lib/api.js` — axios instance at `/api/v1`, Bearer token from `localStorage`. All hooks use this client.
**Frontend state:** `AuthContext` (Supabase session), `LangContext` (en/es toggle), `ThemeContext`. `useSSEQuery.js` drives the streaming chat.
**Admin:** `ADMIN_USER_IDS` env + `is_admin` on profile. `AdminRoute` gates `/admin` and `/admin/queue`. `useDriftReportAdmin` hook for choropleth data.
**Persistence:** Supabase — `chat_sessions`, `chat_messages` (`content_type`: text/advisory/oos, `retrieved_chunks` stored). Drift reports: migration 006.
**Pinecone:** Namespaces by crop (`rice`, `soybean`, `poultry`). Embedding: `all-MiniLM-L6-v2` via `services/embedding.py`.

## F4 Drift Tool
3-step wizard (`components/drift/DriftReportWizard.jsx`). Open-Meteo auto-fill weather. Reportlab PDF (`services/pdf_generator.py`). AR county choropleth (`components/chat/ARCountyMap.jsx`). Migration 006.

## Not Built
Pilot recruitment, Extension outreach, arXiv preprint, NIW package. Vercel/Koyeb deploy. Spanish corpus.
