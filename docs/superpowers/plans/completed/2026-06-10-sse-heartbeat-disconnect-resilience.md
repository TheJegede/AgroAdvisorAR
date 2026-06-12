# SSE Heartbeat + Disconnect Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop novel (uncached) advisory queries from silently vanishing — keep the SSE connection alive during the multi-second LLM call so the Vercel→HF proxy stops reaping it, and guarantee the UI always shows feedback if a stream ever ends without an answer.

**Architecture:** Three independent fixes. (1) Backend `event_stream()` emits an immediate SSE comment then periodic `: keepalive` pings while `run_rag_query` runs as a task — defeats the proxy first-byte/idle timeout that fired at ~6s (`CancelledError` in LangSmith). (2) Backend catches `asyncio.CancelledError` (a `BaseException`, currently uncaught by `except Exception`) so a disconnect frees the in-flight LLM task and propagates cleanly instead of dying mid-generator. (3) Frontend extracts the SSE read loop into a pure, unit-testable `consumeSSEStream` that reports whether any advisory was delivered; if a stream ends empty, the UI shows a retryable error instead of silently clearing the tractor.

**Tech Stack:** FastAPI / Starlette `StreamingResponse` + `asyncio`, pytest. React 19 + Vite, Vitest, Playwright.

---

## Root cause (for context)

LangSmith trace: `CancelledError` ("Cancelled via cancel scope ... RequestResponseCycle.run_asgi()") at **6.06s**, mid-LLM. `event_stream()` (`backend/routers/query.py:146`) awaits `run_rag_query` for the full LLM call yielding **zero bytes**; an idle SSE connection through the Vercel `/api/*` rewrite → HF Space (`frontend/vercel.json`) gets reaped at ~6s. The resulting `CancelledError` is a `BaseException`, so `except Exception` (`query.py:184`) can't emit an error frame; the browser sees a closed stream with nothing delivered and the frontend loop (`useSSEQuery.js:119-149`) ends without adding a message — tractor vanishes, no error. Cached/suggested queries return a first byte instantly (Redis 6h cache) and survive; novel queries don't.

## File Structure

- `backend/routers/query.py` — heartbeat + cancellation handling inside `event_stream()` (Tasks 1, 2).
- `backend/tests/test_query_heartbeat.py` — new test file for heartbeat + cancellation (Tasks 1, 2).
- `frontend/src/hooks/useSSEQuery.js` — extract `consumeSSEStream`, add empty-stream detection + `STREAM_EMPTY_CODE` (Tasks 3, 4).
- `frontend/src/hooks/useSSEQuery.test.js` — unit tests for `consumeSSEStream` (Task 3).
- `frontend/src/pages/ChatPage.jsx` — map `STREAM_EMPTY_CODE` to a friendly message in `onError` (Task 4).
- `frontend/src/constants/i18n.js` — `connectionInterrupted` EN + ES strings (Task 4).
- `frontend/e2e/sse-resilience.spec.js` — new e2e: empty stream → visible retry (Task 5).

---

### Task 1: Backend SSE heartbeat (defeat the idle-timeout disconnect)

**Files:**
- Modify: `backend/routers/query.py` (add `import asyncio`, `HEARTBEAT_INTERVAL_SECONDS`, rewrite `event_stream()`)
- Test: `backend/tests/test_query_heartbeat.py` (create)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_query_heartbeat.py`:

```python
# backend/tests/test_query_heartbeat.py
"""SSE keepalive: an immediate first byte + periodic pings keep the proxy from
reaping the connection during the multi-second LLM call (root cause of the
silent-vanish bug — CancelledError at ~6s)."""
import asyncio
import importlib
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _collect(stream_response):
    async def _run():
        return [chunk async for chunk in stream_response.body_iterator]
    return asyncio.run(_run())


def _blob(frames):
    return "".join(
        c.decode() if isinstance(c, (bytes, bytearray)) else c for c in frames
    )


class _FakeResult:
    confidence_score = 0.5
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


def test_first_frame_is_keepalive(monkeypatch):
    q = importlib.import_module("routers.query")

    async def fake_rag(*a, **k):
        return (_FakeResult(), [])

    _patch_common(q, monkeypatch, fake_rag)
    req = q.QueryRequest(message="why is my rice yellow?", language="en")
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))
    frames = _collect(resp)

    first = frames[0]
    first = first.decode() if isinstance(first, (bytes, bytearray)) else first
    assert first.startswith(": keepalive")


def test_heartbeat_emitted_during_slow_rag(monkeypatch):
    q = importlib.import_module("routers.query")
    monkeypatch.setattr(q, "HEARTBEAT_INTERVAL_SECONDS", 0.01)

    async def fake_rag(*a, **k):
        await asyncio.sleep(0.05)
        return (_FakeResult(), [])

    _patch_common(q, monkeypatch, fake_rag)
    req = q.QueryRequest(message="why is my rice yellow?", language="en")
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))
    blob = _blob(_collect(resp))

    # initial ping + at least one mid-await ping
    assert blob.count(": keepalive") >= 2
    assert '"problem_summary": "ok"' in blob
    assert "[DONE]" in blob
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_query_heartbeat.py -v`
Expected: FAIL — `AttributeError: module 'routers.query' has no attribute 'HEARTBEAT_INTERVAL_SECONDS'` and/or first frame is the advisory data line, not `: keepalive`.

- [ ] **Step 3: Implement the heartbeat in `event_stream()`**

In `backend/routers/query.py`, add `import asyncio` near the top imports (after `import json`):

```python
import asyncio
import json
import logging
```

Add the constant beside the other module constants (after `TRUSTED_HISTORY_LIMIT = 10`):

```python
# SSE keepalive: yield a comment line this often while the LLM call runs so an
# intermediary proxy (Vercel /api/* rewrite -> HF Space) never sees a silent
# connection. Must stay well under the observed ~6s proxy reap timeout.
HEARTBEAT_INTERVAL_SECONDS = 2
```

Replace the entire `event_stream()` body (currently `query.py:146-188`) with:

```python
    async def event_stream():
        # First byte immediately — defeats the proxy first-byte/idle timeout that
        # was reaping the connection at ~6s during the LLM call. Comment lines
        # (starting with ':') are ignored by the SSE client.
        yield ": keepalive\n\n"

        rag_task = asyncio.create_task(
            run_rag_query(
                message=en_message,
                county_fips=county_fips,
                language="en",
                category=category,
                session_history=session_history,
                rice_fields=rice_fields,
                user_id=user["sub"],
            )
        )
        try:
            while not rag_task.done():
                done, _ = await asyncio.wait(
                    {rag_task}, timeout=HEARTBEAT_INTERVAL_SECONDS
                )
                if not done:
                    yield ": keepalive\n\n"

            result, retrieved_chunks = rag_task.result()
            if language == "es":
                result = await translate_advisory_to_es(result, user_id=user["sub"])

            assistant_message_id: str | None = None
            if req.session_id:
                try:
                    save_message(req.session_id, user["sub"], "user", req.message, "text")
                    assistant_row = save_message(
                        req.session_id, user["sub"], "assistant",
                        json.dumps(result.model_dump(), ensure_ascii=False),
                        "advisory",
                        retrieved_chunks=retrieved_chunks,
                        confidence_score=result.confidence_score,
                        escalated=result.escalation is not None,
                    )
                    assistant_message_id = assistant_row["id"]
                except Exception:
                    logger.exception("Failed to persist advisory query response")

            envelope = {
                "advisory": result.model_dump(),
                "message_id": assistant_message_id,
                "category": category,
            }
            payload = json.dumps(envelope, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("Query stream failed")
            error_payload = json.dumps({"error": GENERIC_STREAM_ERROR})
            yield f"data: {error_payload}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            if not rag_task.done():
                rag_task.cancel()
```

> Note: Task 2 adds the `except asyncio.CancelledError` clause to this same block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_query_heartbeat.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the existing stream-error test to confirm no regression**

Run: `cd backend && pytest tests/test_query_stream_error.py -v`
Expected: PASS — the generic-error frame still emits (the leading `: keepalive` comment doesn't touch the `data:` error line the test greps).

- [ ] **Step 6: Commit**

```bash
git add backend/routers/query.py backend/tests/test_query_heartbeat.py
git commit -m "fix(query): SSE heartbeat keeps proxy from reaping the stream mid-LLM"
```

---

### Task 2: Backend — don't swallow `CancelledError`; free the LLM task on disconnect

**Files:**
- Modify: `backend/routers/query.py` (add `except asyncio.CancelledError` to `event_stream()`)
- Test: `backend/tests/test_query_heartbeat.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_query_heartbeat.py`:

```python
def test_cancelled_error_propagates_not_generic(monkeypatch):
    """A client/proxy disconnect (CancelledError) must propagate, not be masked
    as a generic error frame — and the LLM task must be cancelled."""
    q = importlib.import_module("routers.query")

    async def fake_rag(*a, **k):
        raise asyncio.CancelledError()

    _patch_common(q, monkeypatch, fake_rag)
    req = q.QueryRequest(message="why is my rice yellow?", language="en")
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))

    with pytest.raises(asyncio.CancelledError):
        _collect(resp)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_query_heartbeat.py::test_cancelled_error_propagates_not_generic -v`
Expected: FAIL — without an explicit clause, `rag_task.result()` re-raising `CancelledError` is NOT caught by `except Exception`, so it propagates out of the generator... but verify behavior: it may surface as an unhandled task warning or be reported differently. If it already passes by accident, still add Step 3 to make the cancellation + task-cleanup explicit and intentional.

> Note: `asyncio.CancelledError` is a `BaseException`, so the current `except Exception` never touches it. The point of this task is to make the handling **explicit** (cancel the in-flight `rag_task`, then re-raise) so resources are freed and intent is clear.

- [ ] **Step 3: Add the explicit CancelledError clause**

In `event_stream()` (Task 1's block), insert this clause **before** `except Exception:`:

```python
        except asyncio.CancelledError:
            # Client/proxy disconnected — free the in-flight LLM task and let
            # cancellation propagate (do NOT mask as a generic error frame).
            rag_task.cancel()
            raise
        except Exception:
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && pytest tests/test_query_heartbeat.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full query-related suite**

Run: `cd backend && pytest tests/test_query_heartbeat.py tests/test_query_stream_error.py tests/test_query_bridge.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add backend/routers/query.py backend/tests/test_query_heartbeat.py
git commit -m "fix(query): cancel in-flight RAG task and propagate CancelledError on disconnect"
```

---

### Task 3: Frontend — extract `consumeSSEStream` (pure, unit-testable) with empty-stream detection

**Files:**
- Modify: `frontend/src/hooks/useSSEQuery.js` (add exported `consumeSSEStream` + `STREAM_EMPTY_CODE`)
- Test: `frontend/src/hooks/useSSEQuery.test.js` (append)

> The project has no DOM/hook test env, so the read loop is extracted as a pure
> function (same pattern as `parseSSEPayload`, `beginRequest`, `fetchQueryWithAuth`)
> and tested with a fake reader. `consumeSSEStream` returns `true` if at least one
> advisory was delivered, `false` if the stream ended with nothing, and throws on
> a streamed `{error}` frame.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/hooks/useSSEQuery.test.js` (and extend the import on line 2):

```js
import {
  parseSSEPayload,
  beginRequest,
  fetchQueryWithAuth,
  consumeSSEStream,
} from './useSSEQuery'

function readerFrom(chunks) {
  const enc = new TextEncoder()
  let i = 0
  return {
    read: async () =>
      i < chunks.length
        ? { done: false, value: enc.encode(chunks[i++]) }
        : { done: true, value: undefined },
  }
}

describe('consumeSSEStream', () => {
  it('delivers an advisory and reports delivered=true', async () => {
    const onResult = vi.fn()
    const reader = readerFrom([
      `data: ${JSON.stringify({ advisory: { problem_summary: 'ok' }, message_id: 'm1', category: 'IN_SCOPE_RICE:DIAG' })}\n\n`,
      'data: [DONE]\n\n',
    ])

    const delivered = await consumeSSEStream(reader, { onResult })

    expect(delivered).toBe(true)
    expect(onResult).toHaveBeenCalledWith({ problem_summary: 'ok' }, 'm1', 'IN_SCOPE_RICE:DIAG')
  })

  it('reports delivered=false when the stream is only [DONE]', async () => {
    const onResult = vi.fn()
    const reader = readerFrom(['data: [DONE]\n\n'])

    const delivered = await consumeSSEStream(reader, { onResult })

    expect(delivered).toBe(false)
    expect(onResult).not.toHaveBeenCalled()
  })

  it('reports delivered=false when the connection closes with nothing', async () => {
    const onResult = vi.fn()
    const reader = readerFrom([': keepalive\n\n', ': keepalive\n\n'])

    const delivered = await consumeSSEStream(reader, { onResult })

    expect(delivered).toBe(false)
    expect(onResult).not.toHaveBeenCalled()
  })

  it('throws on a streamed error frame', async () => {
    const reader = readerFrom([`data: ${JSON.stringify({ error: 'RAG failed' })}\n\n`])

    await expect(consumeSSEStream(reader, { onResult: vi.fn() })).rejects.toThrow('RAG failed')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/hooks/useSSEQuery.test.js`
Expected: FAIL — `consumeSSEStream is not a function` (not yet exported).

- [ ] **Step 3: Implement `consumeSSEStream` and the constant**

In `frontend/src/hooks/useSSEQuery.js`, add after `parseSSEPayload` (around line 15):

```js
// Returned to onError when a stream ends without delivering an advisory/oos/error.
// ChatPage maps this code to a friendly, localized message.
export const STREAM_EMPTY_CODE = 'stream_empty'

// Reads the SSE body. Returns true if at least one advisory was delivered via
// onResult, false if the stream ended (reader done or [DONE]) with nothing.
// Throws Error(message) on a streamed {error} frame. Comment lines (": ...")
// and malformed payloads are skipped.
export async function consumeSSEStream(reader, { onResult, onCategory }) {
  const decoder = new TextDecoder()
  let buffer = ''
  let delivered = false

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()

    for (const line of lines) {
      if (!line.startsWith('data:')) continue
      const payload = line.slice(5).trim()
      if (payload === '[DONE]') return delivered
      const { parsed, malformed } = parseSSEPayload(payload)
      if (malformed) continue
      if (parsed.error) throw new Error(parsed.error)
      if (parsed.category) onCategory?.(parsed.category)
      onResult(parsed.advisory ?? parsed, parsed.message_id ?? null, parsed.category ?? null)
      delivered = true
    }
  }

  return delivered
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/hooks/useSSEQuery.test.js`
Expected: PASS (all, including the 4 new `consumeSSEStream` cases).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useSSEQuery.js frontend/src/hooks/useSSEQuery.test.js
git commit -m "feat(sse): extract consumeSSEStream with empty-stream detection"
```

---

### Task 4: Frontend — surface a retryable error on empty stream (wire-up + i18n)

**Files:**
- Modify: `frontend/src/hooks/useSSEQuery.js` (use `consumeSSEStream` in `sendQuery`)
- Modify: `frontend/src/pages/ChatPage.jsx` (map `STREAM_EMPTY_CODE` in `onError`)
- Modify: `frontend/src/constants/i18n.js` (add `connectionInterrupted` EN + ES)

- [ ] **Step 1: Replace the inline read loop in `sendQuery`**

In `frontend/src/hooks/useSSEQuery.js`, replace the reader block (currently `useSSEQuery.js:115-140`, from `const reader = res.body.getReader()` through the end of the `while (true) { ... }` loop) with:

```js
      const reader = res.body.getReader()
      const delivered = await consumeSSEStream(reader, { onResult, onCategory })
      if (!delivered) {
        setError(STREAM_EMPTY_CODE)
        setRetryable(true)
        onError?.(STREAM_EMPTY_CODE)
      }
```

> The surrounding `try/catch/finally` is unchanged: a thrown error frame still
> routes to `catch` → `onError`; `AbortError` (deliberate user cancel) still
> returns silently; `finally` still clears `streaming`.

- [ ] **Step 2: Add the `connectionInterrupted` strings**

In `frontend/src/constants/i18n.js`, add to the **English** strings object:

```js
  connectionInterrupted: 'The connection dropped before the answer arrived. Please tap Retry.',
```

And to the **Spanish** strings object:

```js
  connectionInterrupted: 'La conexión se interrumpió antes de recibir la respuesta. Toca Reintentar.',
```

- [ ] **Step 3: Map the code in ChatPage `onError`**

In `frontend/src/pages/ChatPage.jsx`, extend the import on line 4:

```js
import { useSSEQuery, STREAM_EMPTY_CODE } from '../hooks/useSSEQuery'
```

Replace the `onError` handler (currently `ChatPage.jsx:139-145`) with:

```js
      onError: (errMsg) => {
        let display
        if (errMsg === STREAM_EMPTY_CODE) {
          display = t.connectionInterrupted
        } else {
          display = TECHNICAL_ERROR_RE.test(errMsg) ? t.errorGeneric : errMsg
        }
        setMessages((prev) => [
          ...prev,
          makeMessage('assistant', 'error', display),
        ])
      },
```

- [ ] **Step 4: Run unit tests + lint**

Run: `cd frontend && npx vitest run && npm run lint`
Expected: PASS — all vitest green, lint clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useSSEQuery.js frontend/src/pages/ChatPage.jsx frontend/src/constants/i18n.js
git commit -m "feat(chat): show retryable error when SSE stream ends without an answer"
```

---

### Task 5: E2E — empty stream renders a visible retry instead of vanishing

**Files:**
- Create: `frontend/e2e/sse-resilience.spec.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/e2e/sse-resilience.spec.js`:

```js
import { test, expect } from '@playwright/test';
import { injectAuth, mockAppShell, mockChatBackend, submitQuery } from './helpers.js';

test.beforeEach(async ({ page }) => {
  await injectAuth(page);
  await mockAppShell(page);
  await mockChatBackend(page);
  await page.goto('/');
});

test('empty SSE stream shows a retry instead of silently vanishing', async ({ page }) => {
  // Override the query route to return a stream that closes with no advisory —
  // simulates the proxy reaping the connection mid-LLM (the silent-vanish bug).
  await page.unroute('**/api/v1/query');
  await page.route('**/api/v1/query', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'data: [DONE]\n\n',
    });
  });

  await submitQuery(page, 'why does my rice keep getting infested too early on?');

  // The Retry control appears (ChatPage renders it when retryable) and an error
  // message is shown — NOT a silent empty chat.
  await expect(page.getByText(/retry|reintentar/i).first()).toBeVisible({ timeout: 10000 });
  await expect(
    page.getByText(/connection dropped|interrumpió|try again|reintentar/i).first()
  ).toBeVisible({ timeout: 10000 });
});
```

- [ ] **Step 2: Run the test to verify it fails (against pre-fix behavior)**

Run: `npx playwright test e2e/sse-resilience.spec.js` (from `frontend/`)
Expected: FAIL — before Task 4 the empty stream is swallowed (no retry/error text). After Tasks 3–4 are merged it should already pass; if implementing strictly in order, run this AFTER Task 4.

- [ ] **Step 3: Confirm it passes with the fix in place**

Run: `npx playwright test e2e/sse-resilience.spec.js` (from `frontend/`)
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/sse-resilience.spec.js
git commit -m "test(e2e): empty SSE stream surfaces retry, not a silent vanish"
```

---

## Final verification

- [ ] **Backend full suite**

Run: `cd backend && pytest -q`
Expected: all pass (218+ baseline + 3 new heartbeat tests).

- [ ] **Frontend unit + lint**

Run: `cd frontend && npx vitest run && npm run lint`
Expected: all vitest pass, lint clean.

- [ ] **E2E spray + chat + sse**

Run: `npx playwright test e2e/chat.spec.js e2e/sse-resilience.spec.js` (from `frontend/`)
Expected: pass.

---

## Deploy note (owner)

The backend heartbeat fix (Tasks 1–2) only takes effect in prod after an **HF Space backend redeploy** (orphan-branch force-push — see CLAUDE.md Priorities #4). Until then prod keeps reaping idle streams. The frontend fix (Tasks 3–5) deploys via the normal Vercel push and immediately converts any silent vanish into a visible retry. After redeploy, verify by asking a novel (uncached) freeform query and confirming the advisory streams through without the tractor vanishing.

## Self-review notes

- Spec coverage: heartbeat (T1), cancellation safety (T2), frontend empty-stream detection (T3), wire-up + i18n (T4), e2e (T5) — all three reported fixes covered.
- Type/name consistency: `HEARTBEAT_INTERVAL_SECONDS`, `consumeSSEStream`, `STREAM_EMPTY_CODE`, `connectionInterrupted` used consistently across tasks.
- The frontend already tolerates `: keepalive` comment lines (existing `parseSSEPayload` test + the `!line.startsWith('data:')` skip), so backend pings need no frontend change beyond the refactor.
