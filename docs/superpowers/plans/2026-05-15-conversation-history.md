# Conversation History Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist chat sessions and messages in Supabase so conversation history survives page refresh, and let users navigate to a `/sessions` page to resume any past chat.

**Architecture:** Two new Supabase tables (`chat_sessions`, `chat_messages`). Backend gets a `sessions` service + router (`GET/POST /sessions`, `GET /sessions/{id}/messages`). `query.py` saves each user message + advisory response after a successful RAG query. Frontend gets a `useSessions` hook, a `/sessions` list page, a sessions icon in Header, and `ChatPage` reads `?session=<id>` from the URL to load past sessions on mount.

**Tech Stack:** Supabase (PostgreSQL + RLS), FastAPI, Pydantic v2, React 18, React Router v6, TailwindCSS, Axios.

---

## File Map

**New backend files:**
- `backend/models/session.py` — Pydantic request/response schemas
- `backend/services/session.py` — CRUD: create_session, get_sessions, add_message, get_messages
- `backend/routers/sessions.py` — 3 endpoints

**Modified backend files:**
- `backend/main.py` — register sessions router
- `backend/routers/query.py` — add `session_id` field, persist messages after RAG

**New frontend files:**
- `frontend/src/hooks/useSessions.js` — listSessions, createSession, loadSession
- `frontend/src/components/sessions/SessionListItem.jsx` — single session row
- `frontend/src/pages/SessionsPage.jsx` — `/sessions` route page

**Modified frontend files:**
- `frontend/src/constants/i18n.js` — new strings: newChat, pastSessions, noSessions, sessionLoadError, sessions
- `frontend/src/components/layout/Header.jsx` — add sessions icon button
- `frontend/src/App.jsx` — add `/sessions` route + ChatPageWrapper (key on session param)
- `frontend/src/pages/ChatPage.jsx` — session creation on first message, load session from URL
- `frontend/src/hooks/useSSEQuery.js` — accept and pass `sessionId` in request body

---

## Task 1: Supabase Schema

**Files:**
- Run SQL in Supabase dashboard (no code file)

- [ ] **Step 1: Open Supabase SQL Editor**

Go to: Supabase Dashboard → your project → SQL Editor → New query.

- [ ] **Step 2: Run the migration**

```sql
-- chat_sessions: one row per conversation
create table if not exists chat_sessions (
  id               uuid        primary key default gen_random_uuid(),
  user_id          uuid        not null references auth.users(id) on delete cascade,
  preview          text        not null default '',
  message_count    int         not null default 0,
  created_at       timestamptz not null default now(),
  last_message_at  timestamptz not null default now()
);

-- Index for listing sessions newest-first per user
create index if not exists chat_sessions_user_last
  on chat_sessions(user_id, last_message_at desc);

-- chat_messages: one row per turn (user or assistant)
create table if not exists chat_messages (
  id           uuid        primary key default gen_random_uuid(),
  session_id   uuid        not null references chat_sessions(id) on delete cascade,
  user_id      uuid        not null references auth.users(id) on delete cascade,
  role         text        not null check (role in ('user', 'assistant')),
  content      text        not null,
  -- 'text' = user message; 'advisory' = full AdvisoryResponse JSON; 'oos' = out-of-scope string
  content_type text        not null check (content_type in ('text', 'advisory', 'oos')),
  created_at   timestamptz not null default now()
);

-- Index for loading all messages in a session in order
create index if not exists chat_messages_session_order
  on chat_messages(session_id, created_at asc);

-- RLS: users can only see their own data
alter table chat_sessions enable row level security;
create policy "owner_all_sessions" on chat_sessions
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());

alter table chat_messages enable row level security;
create policy "owner_all_messages" on chat_messages
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());
```

- [ ] **Step 3: Verify**

In Supabase → Table Editor, confirm both `chat_sessions` and `chat_messages` tables appear with the correct columns. Click the RLS shield icon on each — both should show "RLS enabled".

---

## Task 2: Backend Pydantic Models

**Files:**
- Create: `backend/models/session.py`

- [ ] **Step 1: Create the file**

```python
# backend/models/session.py
"""Pydantic schemas for session and message endpoints."""
from pydantic import BaseModel


class SessionCreate(BaseModel):
    preview: str = ""


class SessionResponse(BaseModel):
    id: str
    preview: str
    message_count: int
    created_at: str
    last_message_at: str


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str          # 'user' | 'assistant'
    content: str       # raw text for user; JSON string for advisory; plain text for oos
    content_type: str  # 'text' | 'advisory' | 'oos'
    created_at: str


class SessionListResponse(BaseModel):
    sessions: list[SessionResponse]


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
```

- [ ] **Step 2: Verify models parse correctly**

From `backend/` directory:

```bash
python -c "
from models.session import SessionResponse, MessageResponse, SessionListResponse
s = SessionResponse(id='abc', preview='test', message_count=0, created_at='2026-01-01T00:00:00Z', last_message_at='2026-01-01T00:00:00Z')
print('SessionResponse OK:', s.id)
m = MessageResponse(id='xyz', session_id='abc', role='user', content='hello', content_type='text', created_at='2026-01-01T00:00:00Z')
print('MessageResponse OK:', m.role)
print('ALL OK')
"
```

Expected output: `SessionResponse OK: abc`, `MessageResponse OK: user`, `ALL OK`.

---

## Task 3: Backend Session Service

**Files:**
- Create: `backend/services/session.py`

- [ ] **Step 1: Create the service file**

```python
# backend/services/session.py
"""Session and message CRUD. Uses the service-role Supabase client (bypasses RLS).
   Always filter by user_id manually in read operations to prevent cross-user data leaks."""
from datetime import datetime, timezone


def _client():
    from services.user import _get_service_client
    return _get_service_client()


def create_session(user_id: str, preview: str) -> dict:
    result = _client().table("chat_sessions").insert({
        "user_id": user_id,
        "preview": preview[:100].strip(),
    }).execute()
    return result.data[0]


def get_sessions(user_id: str, limit: int = 20) -> list[dict]:
    result = (
        _client()
        .table("chat_sessions")
        .select("*")
        .eq("user_id", user_id)
        .order("last_message_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def add_message(
    session_id: str,
    user_id: str,
    role: str,
    content: str,
    content_type: str,
) -> dict:
    client = _client()
    result = client.table("chat_messages").insert({
        "session_id": session_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "content_type": content_type,
    }).execute()
    now = datetime.now(timezone.utc).isoformat()
    client.table("chat_sessions").update({
        "last_message_at": now,
    }).eq("id", session_id).execute()
    return result.data[0]


def get_messages(session_id: str, user_id: str) -> list[dict] | None:
    client = _client()
    # Manual user_id check because service client bypasses RLS
    ownership = (
        client.table("chat_sessions")
        .select("id")
        .eq("id", session_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if ownership.data is None:
        return None  # not found or not owned by this user
    result = (
        client.table("chat_messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    return result.data
```

- [ ] **Step 2: Smoke-test against live Supabase**

First ensure backend `.env` has real credentials. From `backend/`:

```bash
python -c "
import os; os.chdir('.')
from dotenv import load_dotenv; load_dotenv()
from services.session import create_session, get_sessions, add_message, get_messages

# Use a test user_id (any UUID; won't break anything — just a DB row)
import uuid
fake_user = str(uuid.uuid4())

# This will fail on FK constraint (auth.users requires real user) — that's expected
try:
    create_session(fake_user, 'test preview')
    print('ERROR: expected FK violation')
except Exception as e:
    print('FK constraint caught correctly:', type(e).__name__)

# get_sessions with unknown user should return empty list
sessions = get_sessions(fake_user)
print('get_sessions empty:', sessions == [])

# get_messages with unknown session should return None
msgs = get_messages('00000000-0000-0000-0000-000000000000', fake_user)
print('get_messages None:', msgs is None)
print('ALL OK')
"
```

Expected: `FK constraint caught correctly: ...`, `get_sessions empty: True`, `get_messages None: True`, `ALL OK`.

---

## Task 4: Backend Sessions Router

**Files:**
- Create: `backend/routers/sessions.py`

- [ ] **Step 1: Create the router**

```python
# backend/routers/sessions.py
"""GET /sessions, POST /sessions, GET /sessions/{session_id}/messages"""
from fastapi import APIRouter, Depends, HTTPException
from models.session import (
    SessionCreate, SessionResponse, SessionListResponse,
    MessageListResponse, MessageResponse,
)
from services.auth import get_current_user
from services.session import create_session, get_sessions, get_messages

router = APIRouter()


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(user: dict = Depends(get_current_user)):
    rows = get_sessions(user["sub"])
    return SessionListResponse(sessions=[SessionResponse(**r) for r in rows])


@router.post("/sessions", response_model=SessionResponse, status_code=201)
def new_session(req: SessionCreate, user: dict = Depends(get_current_user)):
    row = create_session(user["sub"], req.preview)
    return SessionResponse(**row)


@router.get("/sessions/{session_id}/messages", response_model=MessageListResponse)
def list_messages(session_id: str, user: dict = Depends(get_current_user)):
    rows = get_messages(session_id, user["sub"])
    if rows is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return MessageListResponse(messages=[MessageResponse(**r) for r in rows])
```

- [ ] **Step 2: Verify syntax**

```bash
cd backend
python -c "from routers.sessions import router; print('Router OK, routes:', [r.path for r in router.routes])"
```

Expected: `Router OK, routes: ['/sessions', '/sessions', '/sessions/{session_id}/messages']`

---

## Task 5: Register Sessions Router in `main.py`

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add import and register router**

In `backend/main.py`, after the existing router imports (line 5–7), add:

```python
from routers.sessions import router as sessions_router
```

After `app.include_router(query_router, prefix="/api/v1")` (line 28), add:

```python
app.include_router(sessions_router, prefix="/api/v1")
```

- [ ] **Step 2: Start backend and verify routes exist**

```bash
cd backend
uvicorn main:app --reload --port 8000
```

In a second terminal:

```bash
curl -s http://localhost:8000/openapi.json | python -c "
import json, sys
spec = json.load(sys.stdin)
paths = [p for p in spec['paths'] if 'session' in p]
print('Session routes:', paths)
"
```

Expected: `Session routes: ['/api/v1/sessions', '/api/v1/sessions/{session_id}/messages']`

---

## Task 6: Modify `query.py` to Persist Messages

**Files:**
- Modify: `backend/routers/query.py`

- [ ] **Step 1: Add `session_id` to `QueryRequest`**

Change `QueryRequest` (lines 15–18) from:

```python
class QueryRequest(BaseModel):
    message: str
    language: str = "en"
    session_history: list[dict] = []
```

To:

```python
class QueryRequest(BaseModel):
    message: str
    language: str = "en"
    session_history: list[dict] = []
    session_id: str | None = None
```

- [ ] **Step 2: Persist messages after successful RAG**

In `event_stream()`, after `result = await run_rag_query(...)` and before `yield f"data: {payload}\n\n"`, insert the save block.

The full updated `event_stream` function (inside the `query` handler) becomes:

```python
    async def event_stream():
        try:
            result = await run_rag_query(
                message=req.message,
                county_fips=county_fips,
                language=language,
                category=category,
                session_history=req.session_history,
            )

            if req.session_id:
                try:
                    from services.session import add_message as _save_msg
                    _save_msg(req.session_id, user["sub"], "user", req.message, "text")
                    _save_msg(
                        req.session_id, user["sub"], "assistant",
                        json.dumps(result.model_dump(), ensure_ascii=False),
                        "advisory",
                    )
                except Exception:
                    pass  # persistence failure must never break the advisory response

            payload = json.dumps(result.model_dump(), ensure_ascii=False)
            yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            error_payload = json.dumps({"error": str(e)})
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"
```

- [ ] **Step 3: Verify end-to-end via curl (requires a real JWT)**

First register + login to get a token (Supabase email confirmation must be OFF):

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"farmer@test.com","password":"testpass123"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

# Create a session
SESSION_ID=$(curl -s -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"preview":"my rice has brown spots"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['id'])")
echo "Session ID: $SESSION_ID"

# Send a query with session_id
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"message\":\"my rice leaves have brown spots\",\"session_history\":[],\"session_id\":\"$SESSION_ID\"}"

# Fetch messages — should return 2 rows (user + assistant)
curl -s "http://localhost:8000/api/v1/sessions/$SESSION_ID/messages" \
  -H "Authorization: Bearer $TOKEN" \
  | python -c "import json,sys; msgs=json.load(sys.stdin)['messages']; print('Message count:', len(msgs)); [print(' -', m['role'], m['content_type']) for m in msgs]"
```

Expected: `Message count: 2`, then `- user text` and `- assistant advisory`.

---

## Task 7: Frontend i18n Strings

**Files:**
- Modify: `frontend/src/constants/i18n.js`

- [ ] **Step 1: Add strings to `en` block**

After `haveAccount: 'Already have an account?',` in the `en` block, add:

```js
    sessions: 'Sessions',
    newChat: 'New Chat',
    pastSessions: 'Past Sessions',
    noSessions: 'No past sessions yet.',
    sessionLoadError: 'Could not load this session.',
    today: 'Today',
    yesterday: 'Yesterday',
```

- [ ] **Step 2: Add strings to `es` block**

After `haveAccount: 'Ya tienes cuenta?',` in the `es` block, add:

```js
    sessions: 'Sesiones',
    newChat: 'Nueva consulta',
    pastSessions: 'Consultas anteriores',
    noSessions: 'Aun no tienes consultas anteriores.',
    sessionLoadError: 'No se pudo cargar esta consulta.',
    today: 'Hoy',
    yesterday: 'Ayer',
```

- [ ] **Step 3: Verify no syntax errors**

```bash
cd frontend
npm run build 2>&1 | head -20
```

Expected: build completes with no errors (or only the existing warnings).

---

## Task 8: Frontend `useSessions` Hook

**Files:**
- Create: `frontend/src/hooks/useSessions.js`

- [ ] **Step 1: Create the hook**

```js
// frontend/src/hooks/useSessions.js
import api from '../lib/api'

export function useSessions() {
  async function listSessions() {
    const res = await api.get('/api/v1/sessions')
    return res.data.sessions // SessionResponse[]
  }

  async function createSession(preview = '') {
    const res = await api.post('/api/v1/sessions', { preview: String(preview).slice(0, 100) })
    return res.data // SessionResponse { id, preview, ... }
  }

  // Returns { messages, sessionHistory } in the format ChatPage expects.
  // messages: { id, role, type, content }[]  (content is parsed for advisory)
  // sessionHistory: { role, content }[]  (last 20 raw turns for RAG context)
  async function loadSession(sessionId) {
    const res = await api.get(`/api/v1/sessions/${sessionId}/messages`)
    const raw = res.data.messages

    const messages = raw.map((m) => ({
      id: m.id,
      role: m.role,
      type: m.content_type,
      content: m.content_type === 'advisory' ? JSON.parse(m.content) : m.content,
    }))

    const sessionHistory = raw.slice(-20).map((m) => ({
      role: m.role,
      content:
        m.content_type === 'advisory'
          ? JSON.parse(m.content).problem_summary
          : m.content,
    }))

    return { messages, sessionHistory }
  }

  return { listSessions, createSession, loadSession }
}
```

- [ ] **Step 2: Verify import resolves**

```bash
cd frontend
node --input-type=module <<'EOF'
import { useSessions } from './src/hooks/useSessions.js'
console.log('import OK:', typeof useSessions)
EOF
```

Expected: `import OK: function`

---

## Task 9: `SessionListItem` + `SessionsPage`

**Files:**
- Create: `frontend/src/components/sessions/SessionListItem.jsx`
- Create: `frontend/src/pages/SessionsPage.jsx`

- [ ] **Step 1: Create the `sessions/` component folder**

No command needed — the `Write` tool will create the path. Just write the files.

- [ ] **Step 2: Write `SessionListItem.jsx`**

```jsx
// frontend/src/components/sessions/SessionListItem.jsx
import { useLang } from '../../contexts/LangContext'

function relativeDate(isoString, t) {
  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now - date
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
  if (diffDays === 0) return t.today
  if (diffDays === 1) return t.yesterday
  return date.toLocaleDateString()
}

export default function SessionListItem({ session, onSelect }) {
  const { t } = useLang()
  return (
    <button
      onClick={() => onSelect(session.id)}
      className="w-full text-left bg-white border border-gray-100 rounded-card px-4 py-3
        min-h-touch hover:border-field hover:bg-field/5 transition-colors flex flex-col gap-0.5"
    >
      <p className="text-sm text-charcoal line-clamp-2 leading-snug">
        {session.preview || '...'}
      </p>
      <p className="text-xs text-gray-400">
        {relativeDate(session.last_message_at, t)}
      </p>
    </button>
  )
}
```

- [ ] **Step 3: Write `SessionsPage.jsx`**

```jsx
// frontend/src/pages/SessionsPage.jsx
import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useLang } from '../contexts/LangContext'
import { useSessions } from '../hooks/useSessions'
import SessionListItem from '../components/sessions/SessionListItem'
import Spinner from '../components/ui/Spinner'
import Button from '../components/ui/Button'
import Alert from '../components/ui/Alert'

export default function SessionsPage() {
  const { t } = useLang()
  const { listSessions } = useSessions()
  const navigate = useNavigate()
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    listSessions()
      .then(setSessions)
      .catch(() => setError(t.errorGeneric))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="max-w-sm mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <Link to="/" className="text-field">
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
          </Link>
          <h1 className="text-xl font-bold text-charcoal">{t.pastSessions}</h1>
        </div>

        <Button
          className="w-full mb-4"
          onClick={() => navigate('/')}
        >
          + {t.newChat}
        </Button>

        {error && <Alert variant="error">{error}</Alert>}
        {loading && <div className="flex justify-center py-8"><Spinner /></div>}
        {!loading && !error && sessions.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-8">{t.noSessions}</p>
        )}
        {!loading && (
          <div className="flex flex-col gap-2">
            {sessions.map((s) => (
              <SessionListItem
                key={s.id}
                session={s}
                onSelect={(id) => navigate(`/?session=${id}`)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
```

---

## Task 10: Add Sessions Icon to `Header.jsx`

**Files:**
- Modify: `frontend/src/components/layout/Header.jsx`

- [ ] **Step 1: Add clock/history icon button**

In `Header.jsx`, after the `<Link to="/profile" ...>` block (ends at the `</Link>` before the logout button, around line 38), insert a sessions link:

```jsx
      <Link
        to="/sessions"
        className="flex items-center justify-center w-10 h-10 rounded-full bg-white/20 hover:bg-white/30 transition-colors"
        aria-label={t.sessions}
      >
        {/* Clock / history icon */}
        <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </Link>
```

The full updated `Header.jsx` file content:

```jsx
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { useLang } from '../../contexts/LangContext'

export default function Header() {
  const { logout } = useAuth()
  const { lang, setLang, t } = useLang()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <header className="h-14 bg-field text-white flex items-center px-4 gap-3 shadow-sm flex-shrink-0">
      <Link to="/" className="flex-1 font-bold text-lg tracking-tight">
        {t.appName}
      </Link>

      <button
        onClick={() => setLang(lang === 'en' ? 'es' : 'en')}
        className="flex items-center gap-1 bg-white/20 hover:bg-white/30 rounded-full px-3 py-1 text-sm font-semibold min-h-touch transition-colors"
        aria-label="Toggle language"
      >
        {lang === 'en' ? 'EN' : 'ES'}
      </button>

      <Link
        to="/sessions"
        className="flex items-center justify-center w-10 h-10 rounded-full bg-white/20 hover:bg-white/30 transition-colors"
        aria-label={t.sessions}
      >
        <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </Link>

      <Link
        to="/profile"
        className="flex items-center justify-center w-10 h-10 rounded-full bg-white/20 hover:bg-white/30 transition-colors"
        aria-label={t.profile}
      >
        <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
        </svg>
      </Link>

      <button
        onClick={handleLogout}
        className="flex items-center justify-center w-10 h-10 rounded-full bg-white/20 hover:bg-white/30 transition-colors"
        aria-label={t.logout}
      >
        <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
        </svg>
      </button>
    </header>
  )
}
```

---

## Task 11: Add `/sessions` Route to `App.jsx`

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Read current `App.jsx` to confirm existing route structure**

Read `frontend/src/App.jsx` before editing.

- [ ] **Step 2: Add import and wrapper for ChatPage + sessions route**

The key change: wrap `ChatPage` in a `ChatPageWrapper` that re-mounts it when the `?session` URL param changes (so loading a past session from the sessions list properly resets state).

The full updated `App.jsx`:

```jsx
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { LangProvider } from './contexts/LangContext'
import AppShell from './components/layout/AppShell'
import ProtectedRoute from './components/ui/ProtectedRoute'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import ChatPage from './pages/ChatPage'
import ProfilePage from './pages/ProfilePage'
import SessionsPage from './pages/SessionsPage'

// Remounts ChatPage when ?session param changes so session state fully resets
function ChatPageWrapper() {
  const location = useLocation()
  const sessionParam = new URLSearchParams(location.search).get('session') ?? 'new'
  return <ChatPage key={sessionParam} />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <LangProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route element={<ProtectedRoute />}>
              <Route element={<AppShell />}>
                <Route path="/" element={<ChatPageWrapper />} />
                <Route path="/profile" element={<ProfilePage />} />
                <Route path="/sessions" element={<SessionsPage />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </LangProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
```

- [ ] **Step 3: Verify dev server starts with no errors**

```bash
cd frontend
npm run dev
```

Open browser at `http://localhost:5173`. No console errors expected. The sessions clock icon should appear in the header. `/sessions` route should render (may be empty list).

---

## Task 12: Modify `useSSEQuery.js` to Accept `sessionId`

**Files:**
- Modify: `frontend/src/hooks/useSSEQuery.js`

- [ ] **Step 1: Add `sessionId` parameter to `sendQuery`**

In `useSSEQuery.js`, change the `sendQuery` destructured params (line 8) from:

```js
  const sendQuery = useCallback(async ({
    message,
    language,
    sessionHistory,
    onResult,
    onOOS,
    onError,
  }) => {
```

To:

```js
  const sendQuery = useCallback(async ({
    message,
    language,
    sessionHistory,
    sessionId,
    onResult,
    onOOS,
    onError,
  }) => {
```

- [ ] **Step 2: Include `session_id` in the request body**

Change the `body: JSON.stringify({...})` call (around line 31) from:

```js
        body: JSON.stringify({
          message,
          language,
          session_history: sessionHistory,
        }),
```

To:

```js
        body: JSON.stringify({
          message,
          language,
          session_history: sessionHistory,
          session_id: sessionId ?? null,
        }),
```

---

## Task 13: Modify `ChatPage.jsx` — Session Creation and Loading

**Files:**
- Modify: `frontend/src/pages/ChatPage.jsx`

This is the largest change. `ChatPage` must now:
1. Read `?session=<id>` from the URL on mount
2. If param present: call `loadSession(id)` to populate messages + sessionHistory
3. If no param: start fresh; create a session on the first message sent
4. Pass `sessionId` to `sendQuery`

- [ ] **Step 1: Write the updated `ChatPage.jsx`**

```jsx
import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useLang } from '../contexts/LangContext'
import { useSSEQuery } from '../hooks/useSSEQuery'
import { useSessions } from '../hooks/useSessions'
import ChatHistory from '../components/chat/ChatHistory'
import ChatInput from '../components/chat/ChatInput'
import Alert from '../components/ui/Alert'
import Spinner from '../components/ui/Spinner'

const EXAMPLE_QUESTIONS = {
  en: [
    'My rice leaves have brown spots — what is wrong?',
    'When should I apply herbicide to my soybeans?',
    'My chickens are losing feathers — is it disease?',
  ],
  es: [
    'Las hojas de mi arroz tienen manchas marrones, que pasa?',
    'Cuando debo aplicar herbicida a la soya?',
    'Mis pollos estan perdiendo plumas, es una enfermedad?',
  ],
}

export default function ChatPage() {
  const { lang, t } = useLang()
  const { sendQuery, streaming } = useSSEQuery()
  const { createSession, loadSession } = useSessions()
  const [searchParams] = useSearchParams()

  const [messages, setMessages] = useState([])
  const [sessionHistory, setSessionHistory] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [loadingSession, setLoadingSession] = useState(false)

  const sessionParam = searchParams.get('session')

  // Load past session from URL param on mount (ChatPageWrapper key forces remount on param change)
  useEffect(() => {
    if (!sessionParam) return
    setLoadingSession(true)
    loadSession(sessionParam)
      .then(({ messages: loaded, sessionHistory: history }) => {
        setMessages(loaded)
        setSessionHistory(history)
        setSessionId(sessionParam)
      })
      .catch(() => setLoadError(t.sessionLoadError))
      .finally(() => setLoadingSession(false))
  }, []) // runs once on mount; remount via key handles param changes

  async function handleSubmit(message) {
    const userMsg = { id: Date.now(), role: 'user', type: 'text', content: message }
    setMessages((prev) => [...prev, userMsg])

    // Create session on first message if we don't have one yet
    let activeSessionId = sessionId
    if (!activeSessionId) {
      try {
        const session = await createSession(message)
        activeSessionId = session.id
        setSessionId(activeSessionId)
      } catch {
        // Session creation failed — proceed without persistence
      }
    }

    const updatedHistory = [...sessionHistory, { role: 'user', content: message }]

    sendQuery({
      message,
      language: lang,
      sessionHistory: updatedHistory,
      sessionId: activeSessionId,
      onResult: (advisory) => {
        setMessages((prev) => [
          ...prev,
          { id: Date.now() + 1, role: 'assistant', type: 'advisory', content: advisory },
        ])
        setSessionHistory((h) => [
          ...h,
          { role: 'user', content: message },
          { role: 'assistant', content: advisory.problem_summary },
        ])
      },
      onOOS: (msg) => {
        setMessages((prev) => [
          ...prev,
          { id: Date.now() + 1, role: 'assistant', type: 'oos', content: msg },
        ])
      },
      onError: (errMsg) => {
        setMessages((prev) => [
          ...prev,
          { id: Date.now() + 1, role: 'assistant', type: 'error', content: errMsg },
        ])
      },
    })
  }

  const examples = EXAMPLE_QUESTIONS[lang] || EXAMPLE_QUESTIONS.en

  if (loadingSession) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {loadError && (
        <div className="px-4 pt-4">
          <Alert variant="error" dismissible>{loadError}</Alert>
        </div>
      )}
      {messages.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center px-6 gap-6 text-center">
          <div>
            <p className="text-3xl mb-2">🌾</p>
            <h1 className="text-xl font-bold text-field mb-1">{t.appName}</h1>
            <p className="text-base text-gray-600">{t.welcomeHeading}</p>
          </div>
          <div className="flex flex-col gap-2 w-full max-w-sm">
            {examples.map((q) => (
              <button
                key={q}
                onClick={() => handleSubmit(q)}
                disabled={streaming}
                className="text-left text-sm bg-white border border-gray-200 rounded-card px-4 py-3
                  hover:border-field hover:bg-field/5 transition-colors min-h-touch text-gray-700"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <ChatHistory messages={messages} streaming={streaming} />
      )}
      <ChatInput onSubmit={handleSubmit} disabled={streaming} />
    </div>
  )
}
```

---

## Task 14: End-to-End Verification

- [ ] **Step 1: Start both servers**

Terminal 1:
```bash
cd backend
uvicorn main:app --reload --port 8000
```

Terminal 2:
```bash
cd frontend
npm run dev
```

- [ ] **Step 2: Test new session creation and persistence**

1. Open `http://localhost:5173` — log in
2. Ask "my rice leaves have brown spots"
3. Advisory card renders
4. Click the clock icon (sessions) in header → `/sessions` page
5. Confirm the session appears with correct preview text and "Today" timestamp

- [ ] **Step 3: Test session resume**

1. On `/sessions` page, click the session
2. Navigates to `/?session=<id>`
3. Chat history shows the previous exchange (user message + advisory card)
4. Ask a follow-up question — it sends correctly

- [ ] **Step 4: Test new chat from sessions page**

1. On `/sessions` page, click "+ New Chat"
2. Navigates to `/` — empty chat screen with example questions
3. Ask a question — creates a new session (separate from the first)
4. Return to `/sessions` — both sessions appear, newest first

- [ ] **Step 5: Test language toggle with loaded session**

1. Load a past session (English)
2. Toggle to ES (header pill)
3. UI strings flip to Spanish; messages remain in original language

- [ ] **Step 6: Verify no console errors in browser DevTools**

Open DevTools → Console tab. No red errors expected during normal flow.

---

## Self-Review Checklist

**Spec coverage:**
- [x] Supabase tables — Task 1
- [x] Backend service CRUD — Task 3
- [x] Backend endpoints (list sessions, create session, list messages) — Task 4
- [x] `query.py` persists messages — Task 6
- [x] Frontend creates session on first message — Task 13
- [x] Frontend loads past session from URL — Task 13
- [x] Sessions list page `/sessions` — Task 9
- [x] Sessions icon in header — Task 10
- [x] "New Chat" navigation — Task 9 (`SessionsPage` button)
- [x] Bilingual strings — Task 7

**Service-role security:** `get_messages` in Task 3 manually filters by `user_id` even though service client bypasses RLS — prevents user A reading user B's messages.

**Failure isolation:** `add_message` failures in `query.py` are swallowed (`except Exception: pass`) — advisory response always reaches the farmer even if persistence fails.

**Type consistency:** `SessionResponse` fields match `chat_sessions` columns. `MessageResponse` fields match `chat_messages` columns. `useSessions.loadSession` maps `content_type` to frontend `type` field correctly.
