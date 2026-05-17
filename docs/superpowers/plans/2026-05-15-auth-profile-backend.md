# Auth + Profile Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Supabase-backed farmer registration, login, JWT auth, and profile management to the FastAPI backend, with the query endpoint pulling `county_fips` from the authenticated farmer's profile.

**Architecture:** Supabase GoTrue handles user creation and token issuance. The FastAPI backend validates Supabase-issued JWTs locally using the `SUPABASE_JWT_SECRET` (no per-request DB call). Farmer profiles live in a `farmer_profiles` Supabase table with RLS. The query endpoint becomes auth-required and reads `county_fips` from the farmer's profile automatically.

**Tech Stack:** FastAPI, Supabase (Postgres + GoTrue), supabase-py, python-jose[cryptography], python-multipart, Pydantic v2

---

## Files Created / Modified

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `backend/requirements.txt` | Add supabase, python-jose, python-multipart |
| Modify | `backend/config.py` | Add SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY, SUPABASE_JWT_SECRET |
| Modify | `.env` | Add 4 new Supabase env vars |
| Modify | `.env.example` | Document new keys |
| Create | `backend/supabase/migrations/001_farmer_profiles.sql` | Schema + RLS policies |
| Create | `backend/models/user.py` | Pydantic schemas: FarmerProfile, RegisterRequest, LoginRequest, UpdateProfileRequest, TokenResponse |
| Create | `backend/services/auth.py` | JWT decode, `get_current_user` FastAPI dependency |
| Create | `backend/services/user.py` | Supabase DB operations for farmer_profiles |
| Create | `backend/routers/auth.py` | POST /auth/register, POST /auth/login |
| Create | `backend/routers/profile.py` | GET /profile, PATCH /profile |
| Modify | `backend/routers/query.py` | Remove `county_fips` from request body, inject from profile |
| Modify | `backend/main.py` | Include auth + profile routers |

---

## Task 1: Create Supabase Project + Collect Keys

**This task is manual — no code.**

- [ ] **Step 1: Create project**
  1. Go to https://supabase.com and sign in
  2. Click **New project**
  3. Name: `AgroAdvisor AR` | Region: `East US (North Virginia)` | Generate a strong DB password → save it
  4. Click **Create new project** — wait ~2 minutes for provisioning

- [ ] **Step 2: Collect API keys**
  1. Go to **Settings → API**
  2. Copy **Project URL** → this is `SUPABASE_URL`
  3. Copy **anon / public** key → this is `SUPABASE_ANON_KEY`
  4. Copy **service_role / secret** key → this is `SUPABASE_SERVICE_KEY`
  5. Scroll to **JWT Settings** → copy **JWT Secret** → this is `SUPABASE_JWT_SECRET`

- [ ] **Step 3: Add to .env**
  Open `C:\Users\jeged\Downloads\AgroAdvisor\.env` and append:
  ```
  SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
  SUPABASE_ANON_KEY=eyJ...
  SUPABASE_SERVICE_KEY=eyJ...
  SUPABASE_JWT_SECRET=your-jwt-secret-here
  ```

- [ ] **Step 4: Update .env.example**
  Append the same keys with placeholder values:
  ```
  SUPABASE_URL=https://your-project-id.supabase.co
  SUPABASE_ANON_KEY=your-anon-key
  SUPABASE_SERVICE_KEY=your-service-role-key
  SUPABASE_JWT_SECRET=your-jwt-secret
  ```

---

## Task 2: Database Schema — farmer_profiles Table

**Files:**
- Create: `backend/supabase/migrations/001_farmer_profiles.sql`

- [ ] **Step 1: Write the migration SQL**

  Create file `backend/supabase/migrations/001_farmer_profiles.sql`:

  ```sql
  -- farmer_profiles: one row per registered farmer
  -- id references auth.users (managed by Supabase GoTrue)
  CREATE TABLE IF NOT EXISTS public.farmer_profiles (
      id            uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
      full_name     text NOT NULL,
      county_fips   char(5) NOT NULL,
      county_name   text NOT NULL,
      primary_crops text[] NOT NULL DEFAULT '{}',
      language      char(2) NOT NULL DEFAULT 'en',
      created_at    timestamptz NOT NULL DEFAULT now(),
      last_active   timestamptz NOT NULL DEFAULT now()
  );

  -- Row Level Security: farmers can only read/write their own row
  ALTER TABLE public.farmer_profiles ENABLE ROW LEVEL SECURITY;

  CREATE POLICY "farmer can read own profile"
      ON public.farmer_profiles FOR SELECT
      USING (auth.uid() = id);

  CREATE POLICY "farmer can insert own profile"
      ON public.farmer_profiles FOR INSERT
      WITH CHECK (auth.uid() = id);

  CREATE POLICY "farmer can update own profile"
      ON public.farmer_profiles FOR UPDATE
      USING (auth.uid() = id);
  ```

- [ ] **Step 2: Run migration in Supabase**
  1. Go to Supabase dashboard → **SQL Editor**
  2. Paste the full SQL above → click **Run**
  3. Confirm: go to **Table Editor** → verify `farmer_profiles` table appears with correct columns

---

## Task 3: Backend Dependencies + Config

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/config.py`

- [ ] **Step 1: Update requirements.txt**

  Add these lines to `backend/requirements.txt`:
  ```
  supabase>=2.4.0
  python-jose[cryptography]>=3.3.0
  python-multipart>=0.0.9
  ```

- [ ] **Step 2: Install new dependencies**

  ```bash
  cd backend
  pip install supabase python-jose[cryptography] python-multipart
  ```

  Expected: packages install without error.

- [ ] **Step 3: Update config.py**

  Replace the contents of `backend/config.py` with:

  ```python
  import os
  from dotenv import load_dotenv

  load_dotenv()

  GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
  PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
  PINECONE_INDEX_NAME = os.environ.get("PINECONE_INDEX_NAME", "agroar-prod")
  UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
  UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
  SENTRY_DSN = os.environ.get("SENTRY_DSN", "")

  SUPABASE_URL = os.environ["SUPABASE_URL"]
  SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
  SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
  SUPABASE_JWT_SECRET = os.environ["SUPABASE_JWT_SECRET"]

  GEMINI_PRIMARY_MODEL = "gemini-2.5-flash"
  GEMINI_CLASSIFIER_MODEL = "gemini-2.5-flash-lite"

  SSURGO_ENDPOINT = "https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest"
  NOAA_POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
  NOAA_USER_AGENT = "AgroAdvisor AR (jegedetaiwo95@gmail.com)"

  REDIS_TTL_SECONDS = 6 * 60 * 60  # 6 hours
  RATE_LIMIT_PER_HOUR = 20
  TOP_K_RETRIEVAL = 5
  MAX_HISTORY_EXCHANGES = 10

  JWT_ALGORITHM = "HS256"
  ```

- [ ] **Step 4: Verify config loads**

  ```bash
  cd backend
  python -c "import config; print('SUPABASE_URL:', config.SUPABASE_URL[:30])"
  ```

  Expected: prints the first 30 chars of your Supabase URL, no errors.

---

## Task 4: Auth Service — JWT Validation + Dependency

**Files:**
- Create: `backend/services/auth.py`

- [ ] **Step 1: Write auth.py**

  Create `backend/services/auth.py`:

  ```python
  """JWT validation and FastAPI auth dependency."""
  from fastapi import Depends, HTTPException, status
  from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
  from jose import JWTError, jwt
  import config

  _bearer = HTTPBearer()


  def decode_token(token: str) -> dict:
      """Decode and validate a Supabase-issued JWT. Raises HTTPException on failure."""
      try:
          payload = jwt.decode(
              token,
              config.SUPABASE_JWT_SECRET,
              algorithms=[config.JWT_ALGORITHM],
              options={"verify_aud": False},  # Supabase tokens have audience "authenticated"
          )
          return payload
      except JWTError as e:
          raise HTTPException(
              status_code=status.HTTP_401_UNAUTHORIZED,
              detail=f"Invalid token: {e}",
              headers={"WWW-Authenticate": "Bearer"},
          )


  def get_current_user(
      credentials: HTTPAuthorizationCredentials = Depends(_bearer),
  ) -> dict:
      """FastAPI dependency — validates JWT and returns the decoded payload.

      Inject with: user: dict = Depends(get_current_user)
      Access user_id with: user["sub"]
      """
      return decode_token(credentials.credentials)
  ```

- [ ] **Step 2: Verify JWT decode works with a real token**

  After Task 6 (auth router) is done, come back and run this. For now, just confirm import works:

  ```bash
  cd backend
  python -c "from services.auth import get_current_user, decode_token; print('auth service OK')"
  ```

  Expected: `auth service OK`

---

## Task 5: User Pydantic Models

**Files:**
- Create: `backend/models/user.py`

- [ ] **Step 1: Write user.py**

  Create `backend/models/user.py`:

  ```python
  """Pydantic schemas for auth and farmer profile endpoints."""
  from pydantic import BaseModel, EmailStr, field_validator
  from typing import Literal
  from utils.counties import AR_COUNTIES


  class RegisterRequest(BaseModel):
      email: EmailStr
      password: str
      full_name: str
      county_fips: str
      primary_crops: list[Literal["rice", "soybeans", "poultry"]] = []
      language: Literal["en", "es"] = "en"

      @field_validator("county_fips")
      @classmethod
      def validate_fips(cls, v: str) -> str:
          if v not in AR_COUNTIES:
              raise ValueError(f"county_fips {v!r} is not a valid Arkansas county FIPS")
          return v

      @field_validator("password")
      @classmethod
      def validate_password(cls, v: str) -> str:
          if len(v) < 8:
              raise ValueError("Password must be at least 8 characters")
          return v


  class LoginRequest(BaseModel):
      email: EmailStr
      password: str


  class TokenResponse(BaseModel):
      access_token: str
      refresh_token: str
      token_type: str = "bearer"


  class FarmerProfile(BaseModel):
      id: str
      full_name: str
      county_fips: str
      county_name: str
      primary_crops: list[str]
      language: str
      created_at: str
      last_active: str


  class UpdateProfileRequest(BaseModel):
      full_name: str | None = None
      county_fips: str | None = None
      primary_crops: list[Literal["rice", "soybeans", "poultry"]] | None = None
      language: Literal["en", "es"] | None = None

      @field_validator("county_fips")
      @classmethod
      def validate_fips(cls, v: str | None) -> str | None:
          if v is not None and v not in AR_COUNTIES:
              raise ValueError(f"county_fips {v!r} is not a valid Arkansas county FIPS")
          return v
  ```

- [ ] **Step 2: Verify models import**

  ```bash
  cd backend
  python -c "from models.user import RegisterRequest, FarmerProfile, TokenResponse; print('models OK')"
  ```

  Expected: `models OK`

---

## Task 6: User Service — Supabase DB Operations

**Files:**
- Create: `backend/services/user.py`

- [ ] **Step 1: Write user.py**

  Create `backend/services/user.py`:

  ```python
  """Farmer profile CRUD against Supabase using the service-role client."""
  from supabase import create_client, Client
  from utils.counties import AR_COUNTIES
  import config

  _service_client: Client | None = None


  def _get_service_client() -> Client:
      """Service-role client bypasses RLS — use only for server-side operations."""
      global _service_client
      if _service_client is None:
          _service_client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
      return _service_client


  def create_profile(
      user_id: str,
      full_name: str,
      county_fips: str,
      primary_crops: list[str],
      language: str,
  ) -> dict:
      county_info = AR_COUNTIES[county_fips]
      county_name = county_info[0]
      client = _get_service_client()
      result = client.table("farmer_profiles").insert({
          "id": user_id,
          "full_name": full_name,
          "county_fips": county_fips,
          "county_name": county_name,
          "primary_crops": primary_crops,
          "language": language,
      }).execute()
      return result.data[0]


  def get_profile(user_id: str) -> dict | None:
      client = _get_service_client()
      result = client.table("farmer_profiles").select("*").eq("id", user_id).single().execute()
      return result.data


  def update_profile(user_id: str, updates: dict) -> dict:
      """updates dict contains only non-None fields from UpdateProfileRequest."""
      if "county_fips" in updates:
          updates["county_name"] = AR_COUNTIES[updates["county_fips"]][0]
      client = _get_service_client()
      result = (
          client.table("farmer_profiles")
          .update(updates)
          .eq("id", user_id)
          .execute()
      )
      return result.data[0]
  ```

- [ ] **Step 2: Verify import**

  ```bash
  cd backend
  python -c "from services.user import get_profile; print('user service OK')"
  ```

  Expected: `user service OK`

---

## Task 7: Auth Router — Register + Login

**Files:**
- Create: `backend/routers/auth.py`

- [ ] **Step 1: Write auth.py router**

  Create `backend/routers/auth.py`:

  ```python
  """Auth endpoints — proxies to Supabase GoTrue for token issuance."""
  from fastapi import APIRouter, HTTPException, status
  from supabase import create_client, Client
  from models.user import LoginRequest, RegisterRequest, TokenResponse
  from services.user import create_profile
  import config

  router = APIRouter(prefix="/auth", tags=["auth"])

  _anon_client: Client | None = None


  def _get_anon_client() -> Client:
      global _anon_client
      if _anon_client is None:
          _anon_client = create_client(config.SUPABASE_URL, config.SUPABASE_ANON_KEY)
      return _anon_client


  @router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
  async def register(body: RegisterRequest):
      client = _get_anon_client()
      try:
          auth_resp = client.auth.sign_up({
              "email": body.email,
              "password": body.password,
          })
      except Exception as e:
          raise HTTPException(status_code=400, detail=str(e))

      if auth_resp.user is None:
          raise HTTPException(status_code=400, detail="Registration failed — check email/password")

      user_id = str(auth_resp.user.id)
      create_profile(
          user_id=user_id,
          full_name=body.full_name,
          county_fips=body.county_fips,
          primary_crops=body.primary_crops,
          language=body.language,
      )

      return TokenResponse(
          access_token=auth_resp.session.access_token,
          refresh_token=auth_resp.session.refresh_token,
      )


  @router.post("/login", response_model=TokenResponse)
  async def login(body: LoginRequest):
      client = _get_anon_client()
      try:
          auth_resp = client.auth.sign_in_with_password({
              "email": body.email,
              "password": body.password,
          })
      except Exception as e:
          raise HTTPException(status_code=401, detail="Invalid email or password")

      if auth_resp.session is None:
          raise HTTPException(status_code=401, detail="Invalid email or password")

      return TokenResponse(
          access_token=auth_resp.session.access_token,
          refresh_token=auth_resp.session.refresh_token,
      )
  ```

- [ ] **Step 2: Wire into main.py temporarily and smoke test register**

  Add to `backend/main.py` (just the import + include for now):
  ```python
  from routers.auth import router as auth_router
  app.include_router(auth_router, prefix="/api/v1")
  ```

  Start server: `uvicorn main:app --reload --port 8000`

  Test register:
  ```bash
  curl -s -X POST http://localhost:8000/api/v1/auth/register \
    -H "Content-Type: application/json" \
    -d '{
      "email": "testfarmer@example.com",
      "password": "testpass123",
      "full_name": "Test Farmer",
      "county_fips": "05055",
      "primary_crops": ["rice", "soybeans"],
      "language": "en"
    }' | python -m json.tool
  ```

  Expected: JSON with `access_token`, `refresh_token`, `token_type`.

- [ ] **Step 3: Test login**

  ```bash
  curl -s -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email": "testfarmer@example.com", "password": "testpass123"}' \
    | python -m json.tool
  ```

  Expected: JSON with `access_token`, `refresh_token`. Save the `access_token` — used in all subsequent tests.

- [ ] **Step 4: Verify decode_token works with real JWT**

  ```bash
  cd backend
  python -c "
  from services.auth import decode_token
  token = 'PASTE_ACCESS_TOKEN_HERE'
  payload = decode_token(token)
  print('user_id:', payload['sub'])
  "
  ```

  Expected: prints your Supabase user UUID.

- [ ] **Step 5: Commit**

  ```bash
  git add backend/routers/auth.py backend/services/auth.py backend/services/user.py \
          backend/models/user.py backend/config.py backend/requirements.txt \
          backend/supabase/migrations/001_farmer_profiles.sql .env.example
  git commit -m "feat: add Supabase auth — register, login, JWT validation"
  ```

---

## Task 8: Profile Router — GET + PATCH

**Files:**
- Create: `backend/routers/profile.py`

- [ ] **Step 1: Write profile.py**

  Create `backend/routers/profile.py`:

  ```python
  """Farmer profile endpoints — all routes require JWT auth."""
  from fastapi import APIRouter, Depends, HTTPException, status
  from models.user import FarmerProfile, UpdateProfileRequest
  from services.auth import get_current_user
  from services.user import get_profile, update_profile

  router = APIRouter(prefix="/profile", tags=["profile"])


  @router.get("", response_model=FarmerProfile)
  async def read_profile(user: dict = Depends(get_current_user)):
      user_id = user["sub"]
      profile = get_profile(user_id)
      if profile is None:
          raise HTTPException(status_code=404, detail="Profile not found")
      return profile


  @router.patch("", response_model=FarmerProfile)
  async def patch_profile(
      body: UpdateProfileRequest,
      user: dict = Depends(get_current_user),
  ):
      user_id = user["sub"]
      updates = body.model_dump(exclude_none=True)
      if not updates:
          raise HTTPException(status_code=400, detail="No fields to update")
      return update_profile(user_id, updates)
  ```

- [ ] **Step 2: Wire into main.py**

  Add to `backend/main.py`:
  ```python
  from routers.profile import router as profile_router
  app.include_router(profile_router, prefix="/api/v1")
  ```

- [ ] **Step 3: Test GET /profile**

  Replace `TOKEN` with the access token from Task 7:
  ```bash
  curl -s http://localhost:8000/api/v1/profile \
    -H "Authorization: Bearer TOKEN" | python -m json.tool
  ```

  Expected:
  ```json
  {
    "id": "...",
    "full_name": "Test Farmer",
    "county_fips": "05055",
    "county_name": "Greene County",
    "primary_crops": ["rice", "soybeans"],
    "language": "en",
    "created_at": "...",
    "last_active": "..."
  }
  ```

- [ ] **Step 4: Test PATCH /profile**

  ```bash
  curl -s -X PATCH http://localhost:8000/api/v1/profile \
    -H "Authorization: Bearer TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"language": "es"}' | python -m json.tool
  ```

  Expected: profile returned with `"language": "es"`.

- [ ] **Step 5: Test invalid FIPS rejected**

  ```bash
  curl -s -X PATCH http://localhost:8000/api/v1/profile \
    -H "Authorization: Bearer TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"county_fips": "99999"}' | python -m json.tool
  ```

  Expected: `422 Unprocessable Entity` with validation error message.

- [ ] **Step 6: Test expired/invalid token rejected**

  ```bash
  curl -s http://localhost:8000/api/v1/profile \
    -H "Authorization: Bearer invalid.token.here" | python -m json.tool
  ```

  Expected: `401 Unauthorized`.

- [ ] **Step 7: Commit**

  ```bash
  git add backend/routers/profile.py backend/main.py
  git commit -m "feat: add profile GET/PATCH endpoints with JWT auth"
  ```

---

## Task 9: Update Query Endpoint — Auth Required, county_fips from Profile

**Files:**
- Modify: `backend/routers/query.py`

- [ ] **Step 1: Read current query.py**

  Read `backend/routers/query.py` to understand the current `QueryRequest` shape before editing.

- [ ] **Step 2: Update QueryRequest — remove county_fips, make language optional**

  In `backend/routers/query.py`, update the `QueryRequest` model:

  ```python
  class QueryRequest(BaseModel):
      message: str
      language: str = "en"
      session_history: list[dict] = []
      # county_fips is now sourced from the authenticated farmer's profile
  ```

- [ ] **Step 3: Update the route handler to require auth and fetch county_fips**

  Update the route function signature and body. The full updated route handler:

  ```python
  from fastapi import APIRouter, Depends
  from fastapi.responses import StreamingResponse
  from pydantic import BaseModel
  from services.auth import get_current_user
  from services.user import get_profile
  from services.classifier import classify_query
  from services.rag import run_rag_query
  from utils.prompt import OUT_OF_SCOPE_MESSAGE
  import json

  router = APIRouter()


  class QueryRequest(BaseModel):
      message: str
      language: str = "en"
      session_history: list[dict] = []


  @router.post("/query")
  async def query(
      body: QueryRequest,
      user: dict = Depends(get_current_user),
  ):
      user_id = user["sub"]
      profile = get_profile(user_id)
      if profile is None:
          from fastapi import HTTPException
          raise HTTPException(status_code=404, detail="Farmer profile not found. Please complete registration.")

      county_fips = profile["county_fips"]

      category = await classify_query(body.message)

      if category == "OUT_OF_SCOPE":
          async def _out_of_scope():
              yield f"data: {json.dumps({'message': OUT_OF_SCOPE_MESSAGE})}\n\ndata: [DONE]\n\n"
          return StreamingResponse(_out_of_scope(), media_type="text/event-stream")

      result = await run_rag_query(
          message=body.message,
          county_fips=county_fips,
          language=body.language,
          category=category,
          session_history=body.session_history,
      )

      async def _stream():
          yield f"data: {result.model_dump_json()}\n\ndata: [DONE]\n\n"

      return StreamingResponse(_stream(), media_type="text/event-stream")
  ```

  > **Note:** Check the existing `query.py` for any additional logic (e.g. rate limiting stubs, Sentry context) and preserve it in the updated version.

- [ ] **Step 4: Test the updated query endpoint with auth**

  First login to get a fresh token:
  ```bash
  TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email": "testfarmer@example.com", "password": "testpass123"}' \
    | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
  ```

  Then query:
  ```bash
  curl -s -X POST http://localhost:8000/api/v1/query \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"message": "my soybeans have yellow leaves", "language": "en", "session_history": []}' 
  ```

  Expected: SSE stream with `problem_summary`, `likely_causes`, `citations`, `context_meta` with `county_fips: "05055"`.

- [ ] **Step 5: Test unauthenticated query is rejected**

  ```bash
  curl -s -X POST http://localhost:8000/api/v1/query \
    -H "Content-Type: application/json" \
    -d '{"message": "my soybeans have yellow leaves"}' | python -m json.tool
  ```

  Expected: `403 Forbidden` (no Bearer header → HTTPBearer returns 403).

- [ ] **Step 6: Commit**

  ```bash
  git add backend/routers/query.py
  git commit -m "feat: query endpoint requires auth, county_fips from farmer profile"
  ```

---

## Task 10: Final main.py Wiring + Smoke Test

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Write the final main.py**

  Replace `backend/main.py` with:

  ```python
  import sentry_sdk
  from fastapi import FastAPI
  from fastapi.middleware.cors import CORSMiddleware
  import config
  from routers.auth import router as auth_router
  from routers.profile import router as profile_router
  from routers.query import router as query_router

  if config.SENTRY_DSN:
      sentry_sdk.init(dsn=config.SENTRY_DSN, traces_sample_rate=0.1)

  app = FastAPI(
      title="AgroAdvisor AR API",
      version="0.2.0",
      description="Arkansas Agricultural AI Advisory System",
  )

  app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],  # tighten when frontend domain is known
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )

  app.include_router(auth_router, prefix="/api/v1")
  app.include_router(profile_router, prefix="/api/v1")
  app.include_router(query_router, prefix="/api/v1")


  @app.get("/health")
  async def health():
      return {"status": "ok", "version": "0.2.0"}
  ```

- [ ] **Step 2: Verify all routes appear in OpenAPI docs**

  Start server: `uvicorn main:app --reload --port 8000`

  Open: http://localhost:8000/docs

  Confirm these routes are listed:
  - `POST /api/v1/auth/register`
  - `POST /api/v1/auth/login`
  - `GET  /api/v1/profile`
  - `PATCH /api/v1/profile`
  - `POST /api/v1/query`
  - `GET  /health`

- [ ] **Step 3: Full E2E flow smoke test**

  ```bash
  # 1. Register new user
  curl -s -X POST http://localhost:8000/api/v1/auth/register \
    -H "Content-Type: application/json" \
    -d '{
      "email": "smoketest@example.com",
      "password": "smokepass123",
      "full_name": "Smoke Test",
      "county_fips": "05001",
      "primary_crops": ["rice"],
      "language": "en"
    }' | python -m json.tool

  # 2. Login
  TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email": "smoketest@example.com", "password": "smokepass123"}' \
    | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

  # 3. Read profile — should show county_fips 05001 (Arkansas County)
  curl -s http://localhost:8000/api/v1/profile \
    -H "Authorization: Bearer $TOKEN" | python -m json.tool

  # 4. Query — county injected automatically from profile
  curl -s -X POST http://localhost:8000/api/v1/query \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"message": "rice blast disease symptoms", "language": "en", "session_history": []}' 
  ```

  Expected: query response shows `"county_fips": "05001"` in `context_meta`, NOAA/SSURGO data for Arkansas County.

- [ ] **Step 4: Final commit**

  ```bash
  git add backend/main.py
  git commit -m "feat: wire all Week 3 routers — auth + profile + authenticated query complete"
  ```

- [ ] **Step 5: Update CLAUDE.md**

  Add to the Commands section of `CLAUDE.md`:
  ```
  ### Auth endpoints
  # Register
  curl -X POST http://localhost:8000/api/v1/auth/register \
    -H "Content-Type: application/json" \
    -d '{"email":"you@example.com","password":"pass123","full_name":"Name","county_fips":"05055","primary_crops":["rice"],"language":"en"}'

  # Login (returns JWT)
  curl -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"you@example.com","password":"pass123"}'

  # Query (requires Bearer token)
  curl -X POST http://localhost:8000/api/v1/query \
    -H "Authorization: Bearer TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message":"rice blast symptoms","language":"en","session_history":[]}'
  ```

---

## Done Criteria (from PRD Week 3)

- [ ] Auth flow end-to-end tested: register → login → profile fetch → query with auth
- [ ] Invalid county FIPS rejected with validation error
- [ ] Invalid/missing JWT returns 401/403
- [ ] Query endpoint uses profile `county_fips`, not request body
- [ ] All 6 routes visible in OpenAPI docs at `/docs`
- [ ] CLAUDE.md updated with new auth curl commands
