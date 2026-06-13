# Latency L1 — SSE Multi-Stage Progress Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Build order: PLAN 3 of 4** (L4 → L2 → **L1** → L3). Build after L2 (no hard code dependency, but L1's frame contract should exist before L3's cache short-circuit). Spec: `docs/superpowers/specs/completed/2026-06-10-sse-progress-streaming-design.md`.

**Goal:** Stream real pipeline-stage progress (Searching → Found N sources + titles → Writing → Verifying) so perceived time-to-first-feedback drops from ~2.8s (blank) to ~0.3s, while the verified advisory still appears only after the guard.

**Architecture:** `run_rag_query` (`backend/services/rag.py`) reports stage transitions onto an optional `asyncio.Queue`; `event_stream` in `routers/query.py` drains the queue concurrently with the rag task, yielding a progress SSE frame per item (keepalive on timeout) and the final advisory frame when the task resolves. Frontend `consumeSSEStream` routes `progress` frames to a new `onProgress`; `ChatPage` holds `progressStage`; a new `QueryProgress.jsx` (folding in the existing tractor `TypingIndicator`) shows a live caption.

**Tech Stack:** Python/FastAPI SSE + asyncio; React 19; vitest (frontend unit); Playwright (e2e). Backend tests use `asyncio.run`.

---

## Background for an engineer with zero context

- **Current backend stream** (`backend/routers/query.py`, function `query` → inner `event_stream`): emits an immediate `": keepalive\n\n"`, creates `rag_task = asyncio.create_task(run_rag_query(...))`, loops `while not rag_task.done()` emitting `": keepalive\n\n"` every `HEARTBEAT_INTERVAL_SECONDS` (=2), then emits ONE `data: {advisory...}` frame and `data: [DONE]`. There is a `CancelledError` branch (re-raise + cancel task) and a generic `Exception` branch (error frame + DONE). `classify_query` runs BEFORE `event_stream` (so `searching` is the first streamed stage).
- **`run_rag_query`** (`backend/services/rag.py`, ~line 324) does, in order: `context_task = create_task(get_context(...))`, `docs = await asyncio.to_thread(_fanout_search, ...)`, optional rerank, `ctx = await context_task`, parse intent, optional AWD, `build_system_prompt`, the provider fallback loop producing `result`, then `advisory = await _postprocess_async(...)` (which runs the guard). Returns `(advisory, retrieved_chunks)`.
- **Frontend SSE consumer** (`frontend/src/hooks/useSSEQuery.js`): `consumeSSEStream(reader, { onResult, onCategory })` parses `data:` lines; `[DONE]` ends; `{error}` throws; otherwise calls `onResult(parsed.advisory ?? parsed, ...)`. `ChatPage.jsx` calls `sendQuery({... onResult, onOOS, onError, onCategory})` and renders `<ChatHistory messages streaming />`. `ChatHistory.jsx:46` renders `{streaming && <TypingIndicator />}` (the tractor). Language via `useLang()` → `{lang, t}` (`contexts/LangContext`); strings in `src/constants/i18n.js`.
- **Backend stream tests** pattern (`backend/tests/test_query_heartbeat.py`): `_patch_common(q, monkeypatch, fake_rag)` patches `classify_query`, `run_rag_query`, `get_profile`, `rate_limit_hit`, `sanitize`; `_collect(resp)` runs `asyncio.run` over `resp.body_iterator`; `_blob(frames)` joins. Reuse these.
- **Frontend tests:** vitest. Run `cd frontend && npx vitest run src/hooks/useSSEQuery.test.js`. Component tests use `@testing-library/react`.

## File Structure

- Modify: `backend/services/rag.py` — `progress: asyncio.Queue | None` param + `_emit` helper + 4 emit calls.
- Modify: `backend/routers/query.py` — queue drain loop in `event_stream`.
- Modify: `frontend/src/hooks/useSSEQuery.js` — `onProgress` route in `consumeSSEStream`; pass `onProgress` through `sendQuery`.
- Create: `frontend/src/components/chat/QueryProgress.jsx` — tractor + live caption (absorbs `TypingIndicator`).
- Modify: `frontend/src/components/chat/ChatHistory.jsx` — render `<QueryProgress stage={progressStage} />`.
- Modify: `frontend/src/pages/ChatPage.jsx` — `progressStage` state + wiring.
- Modify: `frontend/src/constants/i18n.js` — 4 bilingual keys.
- Create: `frontend/src/components/chat/QueryProgress.test.jsx`.
- Create: `frontend/e2e/sse-progress.spec.js`.

---

### Task 1: Backend `_emit` helper + progress param (TDD)

**Files:**
- Modify: `backend/services/rag.py`
- Test: `backend/tests/test_rag_progress.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_rag_progress.py`:

```python
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import rag


def test_emit_puts_when_queue_present():
    async def _run():
        q = asyncio.Queue()
        await rag._emit(q, "searching")
        await rag._emit(q, "sources_found", count=3, titles=["A", "B", "C"])
        return [q.get_nowait(), q.get_nowait()]

    items = asyncio.run(_run())
    assert items[0] == {"stage": "searching"}
    assert items[1] == {"stage": "sources_found", "count": 3, "titles": ["A", "B", "C"]}


def test_emit_noop_when_queue_none():
    async def _run():
        await rag._emit(None, "searching")  # must not raise
        return True
    assert asyncio.run(_run()) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_rag_progress.py -v`
Expected: FAIL — `rag._emit` does not exist.

- [ ] **Step 3: Implement `_emit` and the param**

In `backend/services/rag.py`, add near the top (after imports, `asyncio` already imported):

```python
async def _emit(progress, stage, **data):
    """Put a progress stage dict onto the queue when one is provided; no-op
    otherwise. Lets run_rag_query report stage transitions to the SSE stream
    without coupling to the router."""
    if progress is not None:
        await progress.put({"stage": stage, **data})
```

Change the `run_rag_query` signature to add the keyword-only param (it is already
`*,`-keyword-only):

```python
async def run_rag_query(
    *,
    message: str,
    county_fips: str,
    language: str,
    category: str,
    session_history: list[dict],
    rice_fields: list[dict] | None = None,
    user_id: str | None = None,
    progress: "asyncio.Queue | None" = None,
) -> tuple[AdvisoryResponse, list[dict]]:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_rag_progress.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/rag.py backend/tests/test_rag_progress.py
git commit -m "feat(rag): add _emit progress helper and progress queue param"
```

---

### Task 2: Emit the 4 stages from run_rag_query (TDD)

**Files:**
- Modify: `backend/services/rag.py` — `run_rag_query` body
- Test: `backend/tests/test_rag_progress.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_rag_progress.py`:

```python
class _Doc:
    def __init__(self, title, text):
        self.metadata = {"document_title": title, "section_heading": "Sec"}
        self.page_content = text


def test_run_rag_query_emits_four_stages_in_order(monkeypatch):
    q = asyncio.Queue()
    docs = [_Doc("Rice Disease MP154", "text one"), _Doc("", "text two")]

    monkeypatch.setattr(rag, "_get_vectorstore", lambda: object())
    monkeypatch.setattr(rag, "_fanout_search", lambda vs, m, k, ns: docs)

    async def fake_context(fips):
        return {"soil": {"available": False}, "weather": {"available": False}}
    monkeypatch.setattr(rag, "get_context", fake_context)

    class _Structured:
        async def ainvoke(self, messages, config=None):
            return object()  # _postprocess_async is patched, shape irrelevant

    class _LLM:
        def with_structured_output(self, schema, **kw):
            return _Structured()

    monkeypatch.setattr(rag, "_get_groq_llm", lambda: _LLM())
    monkeypatch.setattr(rag, "_get_deepinfra_llm", lambda: None)
    monkeypatch.setattr(rag, "_get_groq_fast_llm", lambda: None)
    monkeypatch.setattr(rag, "_get_llm", lambda: None)

    async def fake_post(result, docs, soil, weather, county_fips, run_config=None, category=None):
        from models.advisory import AdvisoryResponse, ContextMeta
        return AdvisoryResponse(
            problem_summary="ok", likely_causes=[], recommended_actions=[],
            products_rates=[], warnings=[], citations=[], confidence="High",
            confidence_explanation="x", language="en",
            context_meta=ContextMeta(soil_data_available=False, weather_data_available=False, county_fips=county_fips),
        )
    monkeypatch.setattr(rag, "_postprocess_async", fake_post)

    async def _run():
        await rag.run_rag_query(
            message="soybean seeding rate", county_fips="05055", language="en",
            category="IN_SCOPE_SOYBEANS:INFO", session_history=[], progress=q,
        )
        out = []
        while not q.empty():
            out.append(q.get_nowait())
        return out

    stages = asyncio.run(_run())
    names = [s["stage"] for s in stages]
    assert names == ["searching", "sources_found", "writing", "verifying"]
    sf = next(s for s in stages if s["stage"] == "sources_found")
    assert sf["count"] == 2
    assert sf["titles"] == ["Rice Disease MP154", "Source 2"]  # titleless -> fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_rag_progress.py::test_run_rag_query_emits_four_stages_in_order -v`
Expected: FAIL — no stages emitted yet.

- [ ] **Step 3: Add the 4 emit calls**

In `backend/services/rag.py` `run_rag_query`, insert emits at these points:

1. At the very top of the function body (before `run_config = {...}`):
   ```python
   await _emit(progress, "searching")
   ```
2. Immediately after `docs = await asyncio.to_thread(_fanout_search, ...)` (and after the optional rerank block, before `ctx = await context_task`):
   ```python
   await _emit(
       progress, "sources_found",
       count=len(docs),
       titles=[
           (d.metadata.get("document_title") or f"Source {i+1}")
           for i, d in enumerate(docs)
       ],
   )
   ```
3. Immediately before the provider fallback loop (right before `result = None` / `last_err = None`):
   ```python
   await _emit(progress, "writing")
   ```
4. Immediately before `advisory = await _postprocess_async(...)`:
   ```python
   await _emit(progress, "verifying")
   ```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_rag_progress.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/rag.py backend/tests/test_rag_progress.py
git commit -m "feat(rag): emit searching/sources_found/writing/verifying progress"
```

---

### Task 3: query.py queue drain loop (TDD)

**Files:**
- Modify: `backend/routers/query.py` — `event_stream`
- Test: `backend/tests/test_query_progress.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_query_progress.py`:

```python
import asyncio
import importlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _collect(resp):
    async def _run():
        return [c async for c in resp.body_iterator]
    return asyncio.run(_run())


def _blob(frames):
    return "".join(c.decode() if isinstance(c, (bytes, bytearray)) else c for c in frames)


class _FakeResult:
    confidence_score = 0.9
    escalation = None

    def model_dump(self):
        return {"problem_summary": "ok"}


def _patch_common(q, monkeypatch, fake_rag):
    async def fake_classify(*a, **k):
        return "IN_SCOPE_RICE:DIAG"
    monkeypatch.setattr(q, "classify_query", fake_classify)
    monkeypatch.setattr(q, "run_rag_query", fake_rag)
    monkeypatch.setattr(q, "get_profile", lambda sub: {"county_fips": "05001"})
    monkeypatch.setattr(q, "rate_limit_hit", lambda *a, **k: (True, 19))
    monkeypatch.setattr(q, "sanitize", lambda m: m)


def test_progress_frames_then_advisory_then_done(monkeypatch):
    q = importlib.import_module("routers.query")

    async def fake_rag(*a, progress=None, **k):
        await progress.put({"stage": "searching"})
        await progress.put({"stage": "sources_found", "count": 2, "titles": ["A", "B"]})
        await progress.put({"stage": "writing"})
        await progress.put({"stage": "verifying"})
        return (_FakeResult(), [])

    _patch_common(q, monkeypatch, fake_rag)
    req = q.QueryRequest(message="why is my rice yellow?", language="en")
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))
    blob = _blob(_collect(resp))

    # progress frames present and ordered before the advisory
    i_search = blob.index('"stage": "searching"')
    i_sources = blob.index('"stage": "sources_found"')
    i_writing = blob.index('"stage": "writing"')
    i_verify = blob.index('"stage": "verifying"')
    i_adv = blob.index('"problem_summary": "ok"')
    assert i_search < i_sources < i_writing < i_verify < i_adv
    assert '"titles": ["A", "B"]' in blob
    assert "[DONE]" in blob
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_query_progress.py -v`
Expected: FAIL — the current `event_stream` ignores any progress queue and emits only keepalives + the advisory.

- [ ] **Step 3: Rewrite the drain loop**

In `backend/routers/query.py`, replace the body of `event_stream` from the
`rag_task = asyncio.create_task(...)` line through the `while not rag_task.done(): ...`
heartbeat loop and the `result, retrieved_chunks = rag_task.result()` line with:

```python
        yield ": keepalive\n\n"

        q: asyncio.Queue = asyncio.Queue()
        rag_task = asyncio.create_task(
            run_rag_query(
                message=en_message,
                county_fips=county_fips,
                language="en",
                category=category,
                session_history=session_history,
                rice_fields=rice_fields,
                user_id=user["sub"],
                progress=q,
            )
        )
        try:
            while True:
                if rag_task.done() and q.empty():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_INTERVAL_SECONDS)
                    frame = json.dumps({"progress": item}, ensure_ascii=False)
                    yield f"data: {frame}\n\n"
                except asyncio.TimeoutError:
                    if not rag_task.done():
                        yield ": keepalive\n\n"

            result, retrieved_chunks = rag_task.result()
```

(Keep everything after `result, retrieved_chunks = ...` — the `if language == "es"`
translate, `save_message`, the `envelope`/final `data:` frame, `data: [DONE]`,
and the `except asyncio.CancelledError` / `except Exception` / `finally` blocks —
exactly as they are. Note the original already had a `try:` opening before
`while not rag_task.done()`; you are replacing the loop AND that already-present
`rag_task = create_task(...)`; ensure there is exactly one `try:` wrapping the
drain loop + result handling, matching the original structure.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_query_progress.py tests/test_query_heartbeat.py -v`
Expected: PASS — progress test passes AND the existing heartbeat tests still pass (first frame keepalive, keepalive during slow rag — a slow `fake_rag` that never puts items still yields keepalives; CancelledError still propagates).

- [ ] **Step 5: Commit**

```bash
git add backend/routers/query.py backend/tests/test_query_progress.py
git commit -m "feat(query): drain progress queue into ordered SSE frames"
```

---

### Task 4: Frontend consumeSSEStream onProgress (TDD)

**Files:**
- Modify: `frontend/src/hooks/useSSEQuery.js`
- Test: `frontend/src/hooks/useSSEQuery.test.js`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/hooks/useSSEQuery.test.js` (match the existing import of
`consumeSSEStream` and the reader-mock style already in that file):

```js
function readerFromFrames(frames) {
  const enc = new TextEncoder()
  let i = 0
  return {
    read: async () => {
      if (i >= frames.length) return { done: true, value: undefined }
      return { done: false, value: enc.encode(frames[i++]) }
    },
  }
}

it('routes progress frames to onProgress, advisory to onResult', async () => {
  const progress = []
  const results = []
  const reader = readerFromFrames([
    'data: {"progress":{"stage":"searching"}}\n\n',
    'data: {"progress":{"stage":"sources_found","count":2,"titles":["A","B"]}}\n\n',
    'data: {"advisory":{"problem_summary":"ok"},"message_id":"m1"}\n\n',
    'data: [DONE]\n\n',
  ])
  const delivered = await consumeSSEStream(reader, {
    onResult: (a) => results.push(a),
    onProgress: (p) => progress.push(p),
  })
  expect(progress.map((p) => p.stage)).toEqual(['searching', 'sources_found'])
  expect(progress[1].titles).toEqual(['A', 'B'])
  expect(results).toHaveLength(1)
  expect(delivered).toBe(true)
})

it('progress-only stream reports delivered=false (retry surfaces)', async () => {
  const reader = readerFromFrames([
    'data: {"progress":{"stage":"searching"}}\n\n',
    'data: [DONE]\n\n',
  ])
  const delivered = await consumeSSEStream(reader, { onResult: () => {}, onProgress: () => {} })
  expect(delivered).toBe(false)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/useSSEQuery.test.js`
Expected: FAIL — progress frames currently fall through to `onResult` (no `onProgress` handling).

- [ ] **Step 3: Implement the route**

In `frontend/src/hooks/useSSEQuery.js`, update `consumeSSEStream`'s signature and
add the progress branch BEFORE the `onResult` call:

```js
export async function consumeSSEStream(reader, { onResult, onCategory, onProgress }) {
```

Inside the `for (const line of lines)` loop, after the `if (parsed.error) throw ...`
line and before `if (parsed.category) ...`, add:

```js
      if (parsed.progress) { onProgress?.(parsed.progress); continue }  // not a delivered advisory
```

Then thread `onProgress` through `sendQuery`: add `onProgress` to the destructured
params of `sendQuery`, store it in `lastQueryRef.current`, and pass it to
`consumeSSEStream(reader, { onResult, onCategory, onProgress })`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/hooks/useSSEQuery.test.js`
Expected: PASS (new tests + existing ones).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useSSEQuery.js frontend/src/hooks/useSSEQuery.test.js
git commit -m "feat(sse): route progress frames to onProgress"
```

---

### Task 5: i18n keys + QueryProgress component (TDD)

**Files:**
- Modify: `frontend/src/constants/i18n.js`
- Create: `frontend/src/components/chat/QueryProgress.jsx`
- Create: `frontend/src/components/chat/QueryProgress.test.jsx`

- [ ] **Step 1: Add i18n keys**

In `frontend/src/constants/i18n.js`, add to BOTH the English (`en`) and Spanish
(`es`) string maps (match the existing object shape in that file):

English:
```js
progressSearching: 'Searching extension sources…',
progressFoundSources: 'Found {n} sources',
progressWriting: 'Writing advisory…',
progressVerifying: 'Verifying against sources…',
```
Spanish:
```js
progressSearching: 'Buscando fuentes de extensión…',
progressFoundSources: '{n} fuentes encontradas',
progressWriting: 'Redactando recomendación…',
progressVerifying: 'Verificando con las fuentes…',
```

- [ ] **Step 2: Write the failing test**

Create `frontend/src/components/chat/QueryProgress.test.jsx`:

```jsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'

vi.mock('../../contexts/LangContext', () => ({
  useLang: () => ({
    lang: 'en',
    t: {
      progressSearching: 'Searching extension sources…',
      progressFoundSources: 'Found {n} sources',
      progressWriting: 'Writing advisory…',
      progressVerifying: 'Verifying against sources…',
    },
  }),
}))

import QueryProgress from './QueryProgress'

describe('QueryProgress', () => {
  it('shows the default searching caption when stage is null', () => {
    render(<QueryProgress stage={null} />)
    expect(screen.getByText('Searching extension sources…')).toBeInTheDocument()
  })

  it('shows source count and titles on sources_found', () => {
    render(<QueryProgress stage={{ stage: 'sources_found', count: 2, titles: ['Rice MP154', 'Sheath Blight'] }} />)
    expect(screen.getByText('Found 2 sources')).toBeInTheDocument()
    expect(screen.getByText('Rice MP154')).toBeInTheDocument()
    expect(screen.getByText('Sheath Blight')).toBeInTheDocument()
  })

  it('shows the writing caption', () => {
    render(<QueryProgress stage={{ stage: 'writing' }} />)
    expect(screen.getByText('Writing advisory…')).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/chat/QueryProgress.test.jsx`
Expected: FAIL — `QueryProgress` does not exist.

- [ ] **Step 4: Implement QueryProgress (folds in the tractor)**

Create `frontend/src/components/chat/QueryProgress.jsx`. Move the tractor SVG from
`TypingIndicator.jsx` into a `<Tractor />` block here (copy its `<svg>…</svg>`
verbatim) and add the caption:

```jsx
import { useLang } from '../../contexts/LangContext'

function Tractor() {
  return (
    // PASTE the exact <svg ...>…</svg> markup from TypingIndicator.jsx here.
    <svg viewBox="0 0 120 60" width="96" height="48" className="text-field dark:text-hc-accent" fill="currentColor">
      {/* ...tractor markup copied verbatim from TypingIndicator.jsx... */}
    </svg>
  )
}

export default function QueryProgress({ stage }) {
  const { t } = useLang()
  const name = stage?.stage ?? 'searching'

  let caption = t.progressSearching
  if (name === 'sources_found') caption = (t.progressFoundSources || 'Found {n} sources').replace('{n}', String(stage?.count ?? 0))
  else if (name === 'writing') caption = t.progressWriting
  else if (name === 'verifying') caption = t.progressVerifying

  const titles = name === 'sources_found' ? (stage?.titles ?? []) : []

  return (
    <div
      className="flex flex-col items-center gap-2 p-3 bg-white dark:bg-hc-surface rounded-card shadow-sm border border-gray-100 dark:border-2 dark:border-hc-border w-64 my-2"
      role="status"
      aria-label="Loading response"
    >
      <Tractor />
      <p className="text-sm text-gray-600 dark:text-hc-fg" aria-live="polite">{caption}</p>
      {titles.length > 0 && (
        <ul className="text-xs text-gray-500 dark:text-hc-fg self-stretch list-disc pl-5">
          {titles.map((title, i) => <li key={i}>{title}</li>)}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/chat/QueryProgress.test.jsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/constants/i18n.js frontend/src/components/chat/QueryProgress.jsx frontend/src/components/chat/QueryProgress.test.jsx
git commit -m "feat(chat): QueryProgress stepper with tractor + bilingual captions"
```

---

### Task 6: Wire ChatPage + ChatHistory

**Files:**
- Modify: `frontend/src/pages/ChatPage.jsx`
- Modify: `frontend/src/components/chat/ChatHistory.jsx`

- [ ] **Step 1: ChatPage progress state**

In `frontend/src/pages/ChatPage.jsx`:
- Add state: `const [progressStage, setProgressStage] = useState(null)` (ensure `useState` is imported).
- In the `sendQuery({...})` call, add `onProgress: (p) => setProgressStage(p)`.
- Clear it: at the start of `handleSubmit` set `setProgressStage(null)`; and inside
  `onResult`, `onOOS`, and `onError` callbacks add `setProgressStage(null)` (the
  card/message/error replaces the stepper).
- Pass it down: `<ChatHistory messages={messages} streaming={streaming} progressStage={progressStage} />`.

- [ ] **Step 2: ChatHistory renders QueryProgress**

In `frontend/src/components/chat/ChatHistory.jsx`:
- Change the signature to `export default function ChatHistory({ messages, streaming, progressStage })`.
- Replace `{streaming && <TypingIndicator />}` (line ~46) with:
  ```jsx
  {streaming && <QueryProgress stage={progressStage} />}
  ```
- Add `import QueryProgress from './QueryProgress'` and remove the now-unused
  `import TypingIndicator from './TypingIndicator'`.

- [ ] **Step 3: Delete the orphaned TypingIndicator (its markup now lives in QueryProgress)**

Run: `cd frontend && grep -rl "TypingIndicator" src` — if `ChatHistory.jsx` was the
only importer (expected), delete `src/components/chat/TypingIndicator.jsx` and any
`TypingIndicator.test.*`. If anything else imports it, leave the file and skip this step.

- [ ] **Step 4: Lint + unit run**

Run: `cd frontend && npm run lint && npx vitest run`
Expected: lint clean; all unit tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ChatPage.jsx frontend/src/components/chat/ChatHistory.jsx
git rm --ignore-unmatch frontend/src/components/chat/TypingIndicator.jsx
git commit -m "feat(chat): wire progressStage through ChatPage and ChatHistory"
```

---

### Task 7: E2E — staged progress then advisory

**Files:**
- Create: `frontend/e2e/sse-progress.spec.js`

- [ ] **Step 1: Write the e2e spec**

Create `frontend/e2e/sse-progress.spec.js`. Follow the existing e2e auth/shell-mock
pattern in `frontend/e2e/` (use `injectAuth` + `mockAppShell` helpers if present;
see `frontend/e2e/pwa-offline.spec.js` for the established setup). Mock
`POST /api/v1/query` to return a `text/event-stream` body with staged frames:

```js
// inside the test, after auth + shell mocks:
await page.route('**/api/v1/query', async (route) => {
  const body = [
    'data: {"progress":{"stage":"searching"}}\n\n',
    'data: {"progress":{"stage":"sources_found","count":2,"titles":["Rice MP154","Sheath Blight"]}}\n\n',
    'data: {"progress":{"stage":"writing"}}\n\n',
    'data: {"progress":{"stage":"verifying"}}\n\n',
    'data: {"advisory":{"problem_summary":"Flooded rice nitrogen guidance","likely_causes":[],"recommended_actions":["Apply per label"],"products_rates":[],"warnings":[],"citations":[],"confidence":"High","confidence_explanation":"x","language":"en","context_meta":{"soil_data_available":false,"weather_data_available":false,"county_fips":"05055"}},"message_id":"m1","category":"IN_SCOPE_RICE:DIAG"}\n\n',
    'data: [DONE]\n\n',
  ].join('')
  await route.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream' }, body })
})

// submit a query, then assert the staged captions appear and the advisory renders:
await expect(page.getByText('Found 2 sources')).toBeVisible()
await expect(page.getByText('Rice MP154')).toBeVisible()
await expect(page.getByText('Flooded rice nitrogen guidance')).toBeVisible()
```

- [ ] **Step 2: Run the e2e**

Run: `npx playwright test frontend/e2e/sse-progress.spec.js`
Expected: PASS. (If the staged captions race past too quickly to assert each one,
assert the terminal state: source titles list + the advisory text both visible.)

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/sse-progress.spec.js
git commit -m "test(e2e): SSE staged progress renders then advisory"
```

---

### Task 8: Full regression + manual

- [ ] **Step 1: Backend + frontend suites**

Run: `cd backend && pytest tests/ -k "query or rag or heartbeat" -v` then
`cd frontend && npx vitest run` then `npx playwright test`.
Expected: all green.

- [ ] **Step 2: Manual (optional, needs running app)**

Start backend + frontend, submit a novel query: the tractor shows immediately with
"Searching…", then "Found N sources" + titles, then "Writing…", "Verifying…", then
the advisory card replaces the stepper. Verified advisory still only appears at the
end (never partial unguarded prose).

- [ ] **Step 3: Commit any fixups**

```bash
git add -A && git commit -m "test(l1): regression fixups for progress streaming"
```

---

## Self-Review (completed)

- **Spec coverage:** 4 stages with `sources_found` titles (Tasks 1–2) ✓; queue drain + keepalive fallback + preserved cancel/error paths (Task 3) ✓; `onProgress` route, `delivered` unchanged for progress-only (Task 4) ✓; bilingual captions + titles, tractor kept via `QueryProgress` (Task 5) ✓; ChatPage/ChatHistory wiring + clear-on-result (Task 6) ✓; e2e staged frames (Task 7) ✓; offline unaffected (no offline change) ✓.
- **Placeholders:** the only "paste verbatim" is the tractor SVG copy (Task 5 Step 4) — explicitly the existing `TypingIndicator` markup, not a TODO.
- **Type consistency:** progress dict shape `{stage, count?, titles?}` identical across `_emit` (Task 1), run_rag_query (Task 2), query frame (Task 3), `onProgress` (Task 4), and `QueryProgress` (Task 5); `progress` queue param name consistent rag↔query.
