# AgroAdvisor AR

Bilingual (EN/ES) RAG-powered agricultural advisory system for Arkansas farmers. Targets rice, soybean, and poultry producers, with county-level soil and weather context injected into every response.

The system retrieves from a corpus of University of Arkansas Cooperative Extension publications and combines that evidence with live SSURGO soil data and NOAA weather forecasts to produce structured, cited advisories.

## Architecture

```
┌──────────────┐    ┌──────────────────────────────────────────┐
│  React 19    │    │              FastAPI backend              │
│  Vite + TW   │◄──►│                                           │
│  (frontend)  │SSE │  classifier → context → retriever → LLM   │
└──────────────┘    │                                           │
                    │  • Gemini 2.5 Flash (primary)             │
                    │  • Groq llama-3.3-70b (fallback on 429)   │
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
  → classify message (one of 6 categories; Gemini Flash Lite → Groq fallback)
  → OUT_OF_SCOPE? return static message, no LLM call
  → SAFETY_CRITICAL? proceed with injected safety warning
  → parallel: embed + retrieve (Pinecone, k=5) AND fetch SSURGO + NOAA
  → assemble system prompt (role + conditions + docs + history + instructions)
  → Gemini 2.5 Flash with_structured_output(AdvisoryResponse)
       → Groq llama-3.3-70b fallback on RESOURCE_EXHAUSTED
  → citation guard (strip any citation not matching retrieved doc titles)
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

### Evals

```bash
cd evals
python eval_runner.py --eval-set eval_set_v2.jsonl

# Round 2 pipeline (already in production)
python generate_eval_set_v2.py
python generate_triplets_v2.py
python finetune_v2.py
```

## Environment

Copy `.env.example` to `.env` in the project root and fill in:

| Variable | Purpose |
|----------|---------|
| `GOOGLE_API_KEY` | Gemini API key (Google AI Studio) |
| `GROQ_API_KEY` | Groq fallback for classifier + RAG when Gemini quota is exhausted |
| `PINECONE_API_KEY` | Pinecone serverless |
| `PINECONE_INDEX_NAME` | Defaults to `agroar-prod` (384-dim, cosine, us-east-1) |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_ANON_KEY` | Public anon key (`sb_publishable_…`) |
| `SUPABASE_SERVICE_KEY` | Service-role key — bypasses RLS, server-only |
| `SUPABASE_JWT_SECRET` | Legacy HS256 fallback; ES256 path uses JWKS automatically |
| `UPSTASH_REDIS_REST_URL` / `_TOKEN` | Optional context cache |
| `EMBEDDING_MODEL_PATH` | Defaults to `sentence-transformers/all-MiniLM-L6-v2`; set to `./models/agroar-embeddings-v2` for the fine-tuned model |
| `SENTRY_DSN` | Optional; enables tracing at sample rate 0.1 |

## Key design decisions

- **Structured output.** `with_structured_output(AdvisoryResponse)` uses Gemini's native `response_schema`. No regex or JSON post-parsing. Same pattern on Groq via tool calling.
- **Groq fallback.** Both `services/classifier.py` and `services/rag.py` catch `RESOURCE_EXHAUSTED` from Gemini and transparently retry on Groq `llama-3.3-70b-versatile`. Free tier: 14,400 Groq req/day vs 20 Gemini req/day.
- **County context.** Every query injects county-level soil (SSURGO SDA API) and weather (NOAA NWS API) for the user's `county_fips`. Cached 6h in Upstash Redis. Both APIs must complete in 3s or the response degrades gracefully via `soil_data_available` / `weather_data_available` flags.
- **Citation guard.** After generation, citations are cross-checked against retrieved chunk titles. Unmatched citations are stripped; if none remain, confidence is downgraded to `Low`.
- **Pinecone namespaces.** Documents are upserted by crop (`rice`, `soybeans`, `poultry`, `general`). The classifier output selects the namespace at retrieval time.
- **JWT.** Tokens validated locally — no DB round-trip per request. New Supabase `sb_*` keys use ES256 via JWKS (cached in-process); legacy `eyJ…` keys use HS256.

## Embedding fine-tuning

Two rounds of fine-tuning on `all-MiniLM-L6-v2`. Current production model is `models/agroar-embeddings-v2`, indexed across all 20,546 vectors.

| Metric | v1 (on v2 eval) | v2 mismatched index | v2 matched index | Target |
|--------|-----------------|---------------------|------------------|--------|
| MRR@5  | 0.1666 | 0.2898 | **0.6565** | >0.60 ✓ |
| NDCG@5 | 0.1958 | 0.3197 | **0.6993** | — |
| Hit@1  | 0.105  | 0.225  | **0.530**  | — |
| Hit@5  | 0.285  | 0.410  | **0.825**  | — |

Rollback:

```bash
EMBEDDING_MODEL_PATH=./models/agroar-embeddings-v1 python ingestion/pipeline.py --force
EMBEDDING_MODEL_PATH=sentence-transformers/all-MiniLM-L6-v2 python ingestion/pipeline.py --force
```

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
- **LLMs:** Gemini 2.5 Flash (primary), Groq `llama-3.3-70b-versatile` (fallback)
- **Embeddings:** `sentence-transformers` fine-tuned on agronomy triplets
- **Frontend:** React 19, Vite, TailwindCSS, React Router 7, Axios
- **Storage:** Pinecone (vectors), Supabase Postgres (users + chat history), Upstash Redis (context cache)
- **Data sources:** UA Extension PDFs, USDA SSURGO SDA, NOAA NWS

## License

See repository for license details.
