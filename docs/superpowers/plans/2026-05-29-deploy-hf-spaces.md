# Deploy Plan — Backend on Hugging Face Spaces + Frontend on Vercel

> **For agentic workers:** this is a deployment runbook, not a TDD plan. Steps are
> checkboxes (`- [ ]`). Several steps are **manual** (browser clicks, account
> setup) — those are marked **[YOU]**. Verify each step's expected output before
> moving on.

**Goal:** Get a live production URL — FastAPI backend on Hugging Face Spaces
(free, 16 GB RAM), React frontend on Vercel (free) — wired together.

**Audience note:** written for someone new to HF Spaces + Docker. Concepts are
explained inline.

---

## Background (read once)

- **Docker / Dockerfile:** a Dockerfile is a recipe that builds a "container" — a
  self-contained box with the OS, Python, our code, and dependencies. The host
  runs that box. We write one Dockerfile; HF builds and runs it.
- **Hugging Face Space:** a free hosted app. A "Docker Space" = HF runs *our*
  Dockerfile. It's backed by a **git repo on huggingface.co** — you push code to
  it like GitHub, and it auto-builds + deploys.
- **Why HF Spaces:** free tier = 2 CPU / **16 GB RAM**, no credit card. Our
  backend loads PyTorch + the gte embedding model + the NLI guard (~1.5–2 GB), so
  the 512 MB free tiers (Koyeb/Render) would crash. HF has the headroom.
- **Key HF rule:** a Docker Space must serve HTTP on **port 7860** by default.
- **Ephemeral disk:** the Space's disk resets on restart, and it **sleeps after
  48 h idle** (cold start re-downloads models, ~1–2 min). All real state lives in
  external services (Supabase, Pinecone, Upstash) — we already use those.

---

### Task 1: Backend — Dockerfile + Space config

**Files:**
- Create: `Dockerfile` (repo root)
- Create: `.dockerignore` (repo root)
- Create: `README-space.md` (the HF Space landing page + config header; copied to
  the Space as `README.md` in Task 3)

- [ ] **Step 1: Create `Dockerfile` at the repo root**

```dockerfile
# Backend container for Hugging Face Spaces (Docker SDK).
FROM python:3.11-slim

# System deps some wheels need (torch, sentence-transformers, pinecone, reportlab).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# HF Spaces runs as a non-root user (uid 1000); cache dirs must be writable.
ENV HF_HOME=/tmp/hf \
    SENTENCE_TRANSFORMERS_HOME=/tmp/st \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /app

# Install backend deps first (layer caching: deps change less often than code).
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the backend source.
COPY backend/ /app/

# Pre-download the embedding + NLI models at build time so cold starts are fast
# (otherwise they download on first request). Safe to remove if the build is slow.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('thenlper/gte-base'); \
CrossEncoder('cross-encoder/nli-MiniLM2-L6-H768')"

EXPOSE 7860
# main.py defines `app` (FastAPI). Bind 0.0.0.0:7860 for HF.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
```

- [ ] **Step 2: Create `.dockerignore` at the repo root**

Keeps the image small / build fast by excluding the frontend, models, caches:

```
frontend/
ingestion/
evals/
models/
docs/
.git/
**/__pycache__/
**/*.pyc
.pytest_cache/
*.md
.env
```

- [ ] **Step 3: Create `README-space.md`** (HF reads a YAML header to configure the Space)

```markdown
---
title: AgroAdvisor AR Backend
emoji: 🌾
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

FastAPI backend for AgroAdvisor AR (RAG advisory). Not a user-facing page — the
React frontend on Vercel calls this API.
```

- [ ] **Step 4: Local sanity check (optional but recommended)**

If Docker Desktop is installed:
```bash
docker build -t agroadvisor-backend .
docker run -p 7860:7860 --env-file backend/.env agroadvisor-backend
```
Expected: build succeeds, container logs `Application startup complete`, and
`http://localhost:7860/docs` loads the API docs. (If no Docker locally, skip —
HF will build it.)

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore README-space.md
git commit -m "build: Dockerfile + HF Space config for backend deploy"
```

---

### Task 2: Make the backend bind the HF port + verify health

**Files:**
- Verify/Modify: `backend/main.py`

- [ ] **Step 1: Confirm there is a health route** (HF + smoke tests hit it)

Check `backend/main.py` for a simple GET, e.g. `/` or `/health`. If none exists, add:

```python
@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 2: Confirm CORS reads `CORS_ORIGINS`**

`config.py` already builds `CORS_ORIGINS` from env. The Vercel URL gets added in
Task 4. No code change now — just confirm `main.py` uses `config.CORS_ORIGINS` in
its `CORSMiddleware`.

- [ ] **Step 3: Commit (only if you added /health)**

```bash
git add backend/main.py
git commit -m "feat(backend): /health endpoint for deploy smoke checks"
```

---

### Task 3: Create the Space + push the backend  **[YOU — browser + git]**

- [ ] **Step 1:** Create a free Hugging Face account at https://huggingface.co/join (no card).
- [ ] **Step 2:** New Space → https://huggingface.co/new-space. Set: Owner = you,
  Space name = `agroadvisor-backend`, License = your choice, **SDK = Docker**
  (blank template), Hardware = **CPU basic (free)**, Visibility = Public (free).
- [ ] **Step 3:** HF shows a git URL like
  `https://huggingface.co/spaces/<you>/agroadvisor-backend`. Add it as a remote and
  push. The Space repo needs the Dockerfile at ITS root + `README.md` with the config header:

```bash
# from the AgroAdvisor repo root
git remote add space https://huggingface.co/spaces/<you>/agroadvisor-backend
cp README-space.md README.md      # HF needs README.md with the YAML header
git add README.md && git commit -m "chore: HF Space README"
git push space main
```
- HF asks for a username + an **access token** as the password — create one at
  https://huggingface.co/settings/tokens (role: write).
- **Note:** pushing `main` sends the whole repo, but `.dockerignore` controls what
  goes INTO the image (backend only). The frontend files sit in the Space repo
  unused — harmless. (Cleaner alternative later: a dedicated backend-only repo.)
- [ ] **Step 4:** HF auto-builds. Watch the "Logs" tab on the Space page. Expected:
  Docker build runs, models pre-download, then `Application startup complete`.
  First build is slow (~5–10 min: installs torch + downloads models).

- [ ] **Step 5: Set secrets** **[YOU]** — Space → Settings → "Variables and secrets" → add **Secrets** (encrypted):

  | Secret | Value |
  |---|---|
  | `GROQ_API_KEY` | your Groq key (primary LLM) |
  | `PINECONE_API_KEY` | your Pinecone key |
  | `SUPABASE_URL` | prod Supabase URL |
  | `SUPABASE_ANON_KEY` | prod anon key |
  | `SUPABASE_SERVICE_KEY` | prod service key |
  | `SUPABASE_JWT_SECRET` | prod JWT secret |
  | `GOOGLE_API_KEY` | optional Gemini fallback |
  | `UPSTASH_REDIS_REST_URL` / `_TOKEN` | optional cache |

  And **Variables** (non-secret):

  | Variable | Value |
  |---|---|
  | `LLM_PRIMARY` | `groq` |
  | `EMBEDDING_MODEL_PATH` | `thenlper/gte-base` |
  | `PINECONE_INDEX_NAME` | `agroar-prod-gte` |
  | `RERANK_ENABLED` | `0` (CPU; turn on later if latency is acceptable) |
  | `FRONTEND_URL` | set in Task 4 (password-reset link) |

  > **⚠️ Dim trap — both must be set together.** `config.py` defaults
  > `EMBEDDING_MODEL_PATH` to MiniLM (384-dim). The `agroar-prod-gte` index is
  > 768-dim (gte-base). If you set `PINECONE_INDEX_NAME=agroar-prod-gte` but forget
  > `EMBEDDING_MODEL_PATH=thenlper/gte-base` (or vice versa), retrieval crashes on a
  > vector-dimension mismatch. Set both, or neither.
  >
  > `CORS_ORIGINS` is **not** needed — the Vercel proxy (Task 4) makes all browser
  > calls same-origin. Leave it at its localhost default.

  Adding/changing secrets restarts the Space.

- [ ] **Step 6: Verify the API is live**

Open `https://<you>-agroadvisor-backend.hf.space/health` (or `/docs`).
Expected: `{"status":"ok"}` / the Swagger UI. **This is your backend prod URL.**

---

### Task 4: Frontend on Vercel + wire to the backend  **[YOU — browser + 1 file]**

**Files:**
- Create: `frontend/vercel.json`

**Wiring decision (2026-05-30):** the frontend talks to the backend with a
**relative** base — `/api/v1` — in TWO places: `frontend/src/lib/api.js:4` (axios)
and `frontend/src/hooks/useSSEQuery.js:35` (raw `fetch` for the SSE chat stream).
In dev, Vite's proxy forwards `/api` to the backend. On Vercel there is no proxy,
so we add a **Vercel rewrite** that proxies `/api/*` to the HF backend. This means:
- **No JS change** — both files stay relative and keep working.
- **No CORS** — the browser only ever talks to `agroadvisor.vercel.app`
  (same-origin); Vercel forwards to HF server-side. `CORS_ORIGINS` is irrelevant.
- The `useSSEQuery` raw fetch (the core chat) works without being missed.

- [ ] **Step 1: Routing + API proxy config** — create `frontend/vercel.json`.
  Order matters: the `/api/*` rule must come BEFORE the SPA catch-all, or the
  catch-all swallows API calls into `index.html`.

```json
{
  "rewrites": [
    { "source": "/api/(.*)", "destination": "https://<you>-agroadvisor-backend.hf.space/api/$1" },
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```
(Replace `<you>-agroadvisor-backend.hf.space` with the real HF URL from Task 3
Step 6. The SPA rule serves `index.html` for React Router paths.)

- [ ] **Step 2: Deploy on Vercel** **[YOU]** — https://vercel.com (free, GitHub login):
  - New Project → import the GitHub repo.
  - **Root Directory = `frontend`**. Framework preset = Vite. Build = `npm run build`,
    Output = `dist`.
  - Environment Variables: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` only.
    (No `VITE_API_BASE_URL` — the proxy handles the backend base.)
  - Deploy → you get a URL like `https://agroadvisor.vercel.app`.

- [ ] **Step 3: Set the password-reset redirect** **[YOU]** — in the HF Space
  variables, set `FRONTEND_URL` = `https://agroadvisor.vercel.app` (exact Vercel
  URL). This is the only frontend-aware backend setting still needed — it builds
  the password-reset link in `routers/auth.py`. `CORS_ORIGINS` is NOT needed with
  the proxy; leave it at its default. Space restarts on save.

  > **SSE note:** the chat streams via Server-Sent Events through the Vercel proxy.
  > A proxy can buffer the stream so tokens arrive in chunks (or all at once) rather
  > than smoothly — the final advisory still renders correctly. Confirm in Task 6.

---

### Task 5: Production data prerequisites  **[YOU — one-time]**

- [ ] **Step 1: Supabase migrations** — run any unapplied migrations against the
  PROD Supabase project (SQL editor): `005_alerts.sql`, `007_rice_fields.sql`,
  `008_confidence_scores.sql` (008 already applied earlier — skip if so). Verify no errors.
- [ ] **Step 2: Pinecone index** — confirm `agroar-prod-gte` exists and is populated
  (built this session via `ingestion/ingest_en_gte.py`). The backend's
  `PINECONE_INDEX_NAME` must match.

---

### Task 6: Smoke test the live system  **[YOU]**

- [ ] **Step 1:** Open the Vercel URL, register/login.
- [ ] **Step 2:** Ask an English rice question → expect a populated advisory
  (not a blank/Extension card). Confirms retrieval + Groq generation + guard.
- [ ] **Step 3:** Toggle Spanish, ask a Spanish question → expect a Spanish
  advisory (the translate-bridge). Confirms ES path end to end.
- [ ] **Step 4:** Check the HF Space Logs for errors; check Supabase
  `chat_messages` got the turn. Done = live, working prod URL.

---

## Notes / gotchas

- **Cold start:** after 48 h idle the Space sleeps; the next request takes ~1–2 min
  (container boot + model load). Fine for a pilot. Keep-warm options exist later.
- **Reranker in prod:** `RERANK_ENABLED=0` to start. 16 GB fits the model, but the
  cross-encoder adds CPU latency per query; enable + measure before committing.
- **SSE streaming:** the `/query` endpoint streams; works over HF Spaces (normal
  HTTP). If a proxy buffers it, the frontend still gets the final result.
- **Secrets are never committed** — they live only in HF Space settings + Vercel.
- **First deploy is the hard part;** after that, `git push space main` redeploys.
