# AgroAdvisor AR

[![Nightly retrieval eval](https://github.com/TheJegede/AgroAdvisorAR/actions/workflows/nightly-eval.yml/badge.svg)](https://github.com/TheJegede/AgroAdvisorAR/actions/workflows/nightly-eval.yml)
[![Playwright E2E Tests](https://github.com/TheJegede/AgroAdvisorAR/actions/workflows/playwright.yml/badge.svg)](https://github.com/TheJegede/AgroAdvisorAR/actions/workflows/playwright.yml)
![WCAG 2.1 AA](https://img.shields.io/badge/WCAG_2.1-AA_0_violations-2D6A4F)

Bilingual (EN/ES) RAG-powered agricultural advisory system for Arkansas farmers. Targets rice, soybean, and poultry producers, with county-level soil and weather context injected into every response.

The system retrieves from a corpus of University of Arkansas Cooperative Extension publications and combines that evidence with live SSURGO soil data and NOAA weather forecasts to produce structured, cited advisories.

## Why this exists

Arkansas is one of the top rice and soybean producing states in the US, yet most small and mid-size farm operations lack affordable access to agronomist expertise. Extension agents are thinly spread — 75 counties, one specialist per commodity area at most.

AgroAdvisor AR bridges that gap: a farmer can describe a crop problem in plain English or Spanish and receive a structured advisory grounded in University of Arkansas Extension publications, their county's live soil profile, and current weather conditions — in under 8 seconds, at no cost.

The bilingual interface (EN/ES) extends access to Spanish-speaking agricultural workers and operators who are underserved by existing English-only tools.

## Architecture

```
┌──────────────┐    ┌──────────────────────────────────────────┐
│  React 19    │    │              FastAPI backend              │
│  Vite + TW   │◄──►│                                           │
│  (frontend)  │SSE │  classifier → context → retriever → LLM   │
└──────────────┘    │                                           │
                    │  • Groq llama-3.3-70b (primary)           │
                    │  • Gemini 2.5 Flash (fallback)            │
                    └─────────┬───────────┬───────────┬─────────┘
                              │           │           │
                       ┌──────▼─────┐ ┌───▼────┐ ┌────▼──────┐
                       │  Pinecone  │ │ SSURGO │ │   NOAA    │
                       │ (20.5k vec)│ │  (USDA)│ │   NWS     │
                       └────────────┘ └────────┘ └───────────┘
                              ▲
                              │
                       ┌──────┴─────┐
                       │  Supabase  │  auth + profiles + chat history
                       └────────────┘
```

### Request flow

```
POST /api/v1/query
  → classify message (one of 6 categories; Groq llama-3.1-8b-instant → Gemini fallback)
  → OUT_OF_SCOPE? return static message, no LLM call
  → SAFETY_CRITICAL? proceed with injected safety warning
  → parallel: embed + retrieve (Pinecone, k=5) AND fetch SSURGO + NOAA
  → assemble system prompt (role + conditions + docs + history + instructions)
  → Groq llama-3.3-70b with_structured_output(AdvisoryResponse)
       → fallback chain: 70b → llama-3.1-8b-instant → Gemini 2.5 Flash
  → citation guard: title-match + NLI claim verification; low confidence is
    downgraded or the advisory is suppressed (Extension referral)
  → persist user + assistant turn to chat_messages (if session_id)
  → SSE stream AdvisoryResponse JSON + [DONE]
```

## Components

| Path          | Purpose |
|---------------|---------|
| `backend/`    | FastAPI app: routers, services (classifier, RAG, context, auth, sessions), Pydantic models |
| `frontend/`   | React 19 + Vite + TailwindCSS chat UI with sidebar layout |
| `ingestion/`  | PDF scraper, extractor, chunker, embedder, Pinecone upsert pipeline |
| `evals/`      | Eval-set generator, triplet miner, embedding fine-tune scripts, MRR/NDCG runner |
| `docs/`       | Internal design notes |
| `AgroAdvisor_AR_PRD_v2.md` | Canonical product spec |

## Quickstart

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                # vite on :5173, proxies /api → :8000
```

### Ingestion

```bash
cd ingestion
pip install -r requirements.txt
python scraper.py          # download UA Extension PDFs
python pipeline.py         # chunk, embed, upsert to Pinecone
python pipeline.py --force # re-index unchanged docs
```

**Spanish = translate-bridge.** There is no dedicated Spanish corpus or index.
A Spanish query is translated to English (`services/translation.py`, LLM), runs
through the English RAG pipeline unchanged, and the answer's user-facing prose is
translated back to Spanish. Validated: ES→EN→gte retrieval recall matches the
English-direct baseline. See `docs/superpowers/specs/2026-05-29-spanish-translate-bridge-design.md`.

### Evals

```bash
cd evals
python eval_runner.py --eval-set eval_set_v2.jsonl       # retrieval metrics
python answer_eval_full.py --provider local --sample 20  # end-to-end (local GPU)

# Honest, disjoint fine-tuning pipeline (training set excludes eval gold chunks):
python generate_synthetic_queries.py --lang en --sample-chunks 2000
python finetune_synth.py --lang en

# NOTE: generate_triplets_v2.py / finetune_v2.py are the legacy round-2 recipe.
# They train on eval_set_v2.jsonl, so metrics from them are train-on-test — do
# not report them. Kept only for historical reference.
```

Spanish eval generation uses `evals/build_es_eval.py`, which also depends on
the eval requirements rather than the backend runtime requirements.

## Environment

Copy `.env.example` to `.env` in the project root and fill in:

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | **Primary** LLM provider (generation, classifier, claim decomposition) |
| `GOOGLE_API_KEY` | Gemini — optional fallback only (free tier is 20 req/day) |
| `LLM_PRIMARY` | Provider order; defaults to `groq` (`gemini` to flip) |
| `RERANK_ENABLED` | Optional cross-encoder reranking; off by default (heavy for free-tier CPU) |
| `PINECONE_API_KEY` | Pinecone serverless |
| `PINECONE_INDEX_NAME` | Defaults to `agroar-prod` (384-dim, cosine, us-east-1) |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_ANON_KEY` | Public anon key (`sb_publishable_…`) |
| `SUPABASE_SERVICE_KEY` | Service-role key — bypasses RLS, server-only |
| `SUPABASE_JWT_SECRET` | Legacy HS256 fallback; ES256 path uses JWKS automatically |
| `UPSTASH_REDIS_REST_URL` / `_TOKEN` | Optional context cache |
| `EMBEDDING_MODEL_PATH` | Defaults to `sentence-transformers/all-MiniLM-L6-v2`; set to `./models/agroar-embeddings-v2` for the fine-tuned model |
| `NLI_CITATION_GUARD_ENABLED` | Defaults to `1`; set to `0` to disable claim-level NLI verification in constrained runtimes |
| `SENTRY_DSN` | Optional; enables tracing at sample rate 0.1 |

## Key design decisions

- **Structured output.** `with_structured_output(AdvisoryResponse)` via Groq tool calling (primary), Gemini `response_schema` as fallback. No regex or JSON post-parsing.
- **Groq-primary, provider chain.** `classifier.py`, `rag.py`, and `citation_guard_v2.py` try providers in order (default Groq first, Gemini fallback) and degrade gracefully. Gemini's free tier is 20 req/day, so Groq is primary. Note: Groq's free tier has per-day **token** caps too — generation falls back 70b → 8b-instant to stretch them; a second free provider may be needed for sustained load.
- **County context.** Every query injects county-level soil (SSURGO SDA API) and weather (NOAA NWS API) for the user's `county_fips`. Cached 6h in Upstash Redis. Both APIs must complete in 3s or the response degrades gracefully via `soil_data_available` / `weather_data_available` flags.
- **Citation guard.** After generation, citations are cross-checked against retrieved chunk titles. Unmatched citations are stripped; if none remain, confidence is downgraded to `Low`.
- **Pinecone namespaces.** Documents are upserted by crop (`rice`, `soybeans`, `poultry`, `general`). The classifier output selects the namespace at retrieval time.
- **JWT.** Tokens validated locally — no DB round-trip per request. New Supabase `sb_*` keys use ES256 via JWKS (cached in-process); legacy `eyJ…` keys use HS256.

## Retrieval evaluation

> **Correction:** an earlier version of this README reported `MRR@5 0.6565` for
> the fine-tuned `agroar-embeddings-v2` model. That number was **invalid** — the
> model was fine-tuned on the same 200 items it was evaluated on (train-on-test).
> Verified honest held-out (5-fold) exact-match MRR@5 for that model is ~0.18,
> essentially the un-fine-tuned base. The `generate_triplets_v2.py` →
> `finetune_v2.py` recipe builds its training triplets from `eval_set_v2.jsonl`,
> so any metric it produces against that set is contaminated. Do not cite it.

Honest measurement is ongoing in `evals/`:

- **Exact single-id metrics undercount badly** on this corpus — ~79% of labeled
  gold chunks have near-duplicates, so the retriever often returns an
  equally-valid chunk that is scored as a miss.
- Under **relevance-based judging** (LLM-as-judge over what was retrieved), the
  best offline pipeline — `gte-base` embeddings + `bge-reranker-v2-m3` reranking —
  reaches roughly **MRR@5 ≈ 0.6, hit@5 ≈ 0.8** on the 200-item held-out set.
  This uses a small local judge (noisy) and is not yet human-validated.
- A **disjoint** synthetic-query fine-tuning pipeline (`generate_synthetic_queries.py`
  + `finetune_synth.py`) gives a small but *real* held-out lift, unlike the
  contaminated recipe above.

The **deployed** EN index uses `all-MiniLM-L6-v2` without reranking and scores
lower than the gte-base + reranker pipeline, which is not yet in production.

Rollback / model selection via `EMBEDDING_MODEL_PATH`:

```bash
EMBEDDING_MODEL_PATH=sentence-transformers/all-MiniLM-L6-v2 python ingestion/pipeline.py --force
```

## Security

- **Brute-force protection.** Login attempts rate-limited to 10 per 15 minutes per email (Redis; fail-open if Redis unavailable).
- **Query rate limiting.** 20 queries/hour/user via Redis key `query_throttle:{user_id}`. Returns 429 + `Retry-After: 3600`.
- **Prompt injection sanitizer.** `services/sanitizer.py` rejects high-confidence injection attempts (role override, instruction-ignore, literal role tokens `<|im_start|>`, `<system>`, `[INST]`) and silently strips lower-risk patterns. Tuned to avoid false positives on natural phrases.
- **CORS.** Locked to `CORS_ORIGINS` env var — no wildcard origin in production.
- **OWASP Top 10.** Audited 2026-05-16; one critical finding (A07 — missing login rate limit) identified and resolved.

## Accessibility

WCAG 2.1 AA verified with axe-core across all six routes (`/login`, `/register`, `/`, `/profile`, `/admin`, `/admin/queue`): **0 violations**.

High-contrast mode available via sidebar toggle — sets `data-theme="hc"` on `<html>`, persists in `localStorage`. Tested in both light and HC modes.

## API

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/api/v1/auth/register` | Creates Supabase user + `farmer_profiles` row, returns tokens |
| `POST` | `/api/v1/auth/login` | Email + password, returns tokens |
| `GET`  | `/api/v1/profile` | Bearer token required |
| `PATCH`| `/api/v1/profile` | Update profile |
| `POST` | `/api/v1/query` | RAG query, SSE stream, persists turn if `session_id` provided |
| `POST` | `/api/v1/sessions` | Create chat session |
| `GET`  | `/api/v1/sessions` | List user's sessions (newest 20) |
| `GET`  | `/api/v1/sessions/{id}/messages` | List messages for session |

See `CLAUDE.md` for `curl` examples.

## Tech stack

- **Backend:** FastAPI, LangChain, Pinecone, Supabase, Pydantic v2, Sentry
- **LLMs:** Groq `llama-3.3-70b-versatile` + `llama-3.1-8b-instant` (primary), Gemini 2.5 Flash (fallback)
- **Embeddings:** `thenlper/gte-base` (EN retrieval, index `agroar-prod-gte`) + `bge-reranker-v2-m3`; Spanish via translate-bridge (no separate ES embeddings)
- **Frontend:** React 19, Vite, TailwindCSS, React Router 7, Axios
- **Storage:** Pinecone (vectors), Supabase Postgres (users + chat history), Upstash Redis (context cache)
- **Data sources:** UA Extension PDFs, USDA SSURGO SDA, NOAA NWS

## License

MIT
