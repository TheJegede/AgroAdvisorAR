# SSE Multi-Stage Progress Streaming (Latency Lever 1)

**Date:** 2026-06-10
**Status:** Design approved, pending spec review
**Lever:** Answer-latency lever 1 of the measured plan (see `backend/scripts/latency_probe.py`).

## Problem

A `/api/v1/query` request shows the user **nothing** until the entire pipeline
finishes. `routers/query.py` buffers the whole advisory and emits a single SSE
`data:` frame at the end (`query.py:203`); the in-flight heartbeats are empty
`: keepalive` comment lines carrying no content. The animated tractor
(`TypingIndicator`) spins over a silent wait.

### Measured latency (warm, EN, `backend/scripts/latency_probe.py`)

| stage | avg ms | notes |
|---|---|---|
| classify | 254 | LLM #1 (runs before the stream opens, `query.py:131`) |
| embed | 27 | gte-base, CPU — negligible |
| retrieve | 89 | Pinecone ANN — negligible |
| context | 2119 | concurrent w/ retrieve + 6h cached — OFF critical path (mostly NOAA timeout) |
| generate | 1239 | LLM #2 |
| guard | 1262 | LLM #3 + #4 (`decompose_claims` then `judge_claims_llm`, serial) |
| **SERIAL** | **~2845** | classify+retrieve+generate+guard; range 1129–4968 |

Retrieval is NOT the bottleneck. Generate + guard (both LLM, both serial) are
~88% of the wait. The user perceives the full ~2.8s as a blank screen.

## Goal & non-goals

**Goal:** cut **perceived** time-to-first-feedback from ~2.8s (blank) to ~0.3s
by streaming real pipeline-stage progress, including the titles of the source
documents being read, while the verified advisory still appears only after the
guard passes.

**Non-goals (YAGNI):**
- No reduction of actual content latency (that is lever 2 = conditional/parallel
  guard, and lever 3 = answer cache). Verified advisory still lands at ~2.8s.
- No token-level streaming of advisory prose — the LLM uses
  `with_structured_output`, which blocks until the full object is built.
- No streaming of unverified content. The guard can suppress an ungrounded or
  low-confidence body (`rag.py:309`); for a pesticide-rate app we must never
  flash content the guard would retract. **Safety posture: progress frames only;
  advisory body shown only after the guard runs.**
- No per-provider progress, no client-side % estimates (real stage signal only).
- No guard bypass (lever 2).

## Latency impact

| | Before | After lever 1 |
|---|---|---|
| First feedback (perceived TTFT) | blank ~2.8s | ~0.3s ("Searching…") |
| Sees which sources are read | never | ~0.4s (titles) |
| Verified advisory | ~2.8s | ~2.8s (unchanged) |
| Queue-drain overhead | — | sub-millisecond |

## Architecture — Approach A (async queue)

`run_rag_query` reports stage transitions to the SSE generator through an
optional `asyncio.Queue`. Chosen over (B) converting `run_rag_query` to an async
generator (breaks the tuple return contract for every caller/test) and (C)
frontend-only fake staging (misleading — would show "Verifying" while still
generating). Approach A is non-breaking (optional param, same return) and folds
the existing heartbeat into one drain loop.

### Stages

| stage code | emitted when | payload | ~elapsed |
|---|---|---|---|
| `searching` | `run_rag_query` entry | `{}` | 0s |
| `sources_found` | after `_fanout_search` | `{count, titles[]}` | ~0.4s |
| `writing` | before the provider loop | `{}` | ~0.5s |
| `verifying` | before `_postprocess_async` | `{}` | ~1.7s |
| *(final advisory)* | task resolves | `{advisory, message_id, category}` | ~2.8s |

`titles` = each retrieved doc's `document_title`, fallback `"Source N"` for
titleless chunks. `count` = number of retrieved docs.

## Backend

### `services/rag.py`

Add optional param and a small emit helper. Same tuple return — non-breaking.

```python
async def _emit(progress, stage, **data):
    if progress is not None:
        await progress.put({"stage": stage, **data})

async def run_rag_query(*, ..., progress: asyncio.Queue | None = None):
    await _emit(progress, "searching")
    ...
    docs = await asyncio.to_thread(_fanout_search, ...)
    await _emit(progress, "sources_found",
                count=len(docs),
                titles=[d.metadata.get("document_title") or f"Source {i+1}"
                        for i, d in enumerate(docs)])
    ...
    await _emit(progress, "writing")          # before the provider loop
    result = ... (provider loop unchanged) ...
    await _emit(progress, "verifying")        # before the guard
    advisory = await _postprocess_async(...)
    return advisory, retrieved_chunks
```

`writing` is emitted once before the provider fallback loop, not per provider.

### `routers/query.py`

`event_stream` replaces the blind heartbeat loop with a queue drain:

```python
yield ": keepalive\n\n"                      # immediate first byte (kept)
q = asyncio.Queue()
rag_task = asyncio.create_task(run_rag_query(..., progress=q))
try:
    while True:
        if rag_task.done() and q.empty():
            break
        try:
            item = await asyncio.wait_for(q.get(), timeout=HEARTBEAT_INTERVAL_SECONDS)
            yield f"data: {json.dumps({'progress': item}, ensure_ascii=False)}\n\n"
        except asyncio.TimeoutError:
            if not rag_task.done():
                yield ": keepalive\n\n"

    result, retrieved_chunks = rag_task.result()   # raises -> except path
    # ...existing: ES translate_advisory_to_es, save_message,
    #    final advisory envelope frame, "data: [DONE]\n\n"
except asyncio.CancelledError:
    rag_task.cancel()
    raise
except Exception:
    logger.exception("Query stream failed")
    yield f"data: {json.dumps({'error': GENERIC_STREAM_ERROR})}\n\n"
    yield "data: [DONE]\n\n"
finally:
    if not rag_task.done():
        rag_task.cancel()
```

Keepalive stays as the >2s fallback (generate/guard exceed the interval).
CancelledError (client disconnect) and Exception paths preserve current
behavior (`query.py:205-217`).

### Frame schemas

- Progress: `data: {"progress":{"stage":"sources_found","count":5,"titles":[...]}}`
- Final (unchanged): `data: {"advisory":{...},"message_id":...,"category":...}`
- `data: [DONE]` (unchanged)

## Frontend

### `hooks/useSSEQuery.js`

`consumeSSEStream(reader, { onResult, onCategory, onProgress })`:

```js
if (parsed.progress) { onProgress?.(parsed.progress); continue }  // does NOT set delivered
```

Progress frames must NOT set `delivered`, so a stream that emits only progress
then ends still triggers `STREAM_EMPTY_CODE` retry (correct — no advisory was
delivered). Missing fields must not throw.

### `pages/ChatPage.jsx`

- New `progressStage` state.
- `onProgress: (p) => setProgressStage(p)`.
- Clear `progressStage` in `onResult`, `onOOS`, `onError` (card/message replaces it).
- Pass `progressStage` down to `ChatHistory`.

### `components/chat/ChatHistory.jsx` + `QueryProgress.jsx`

Today: `{streaming && <TypingIndicator />}` (`ChatHistory.jsx:46`).

**Keep the tractor.** Fold `TypingIndicator` into a new `QueryProgress.jsx`:
the tractor SVG stays as the animated visual, with a live caption beneath it
that updates per stage and lists source titles on `sources_found`.

```
{streaming && <QueryProgress stage={progressStage} />}
```

- `stage == null` (streaming started, no frame yet) → tractor + default caption
  (`t.progressSearching`). No gap.
- `searching` → tractor + `t.progressSearching`.
- `sources_found` → tractor + `t.progressFoundSources` (with `count`) + titles list.
- `writing` → tractor + `t.progressWriting`.
- `verifying` → tractor + `t.progressVerifying`.

Captions localized via `t` (EN/ES). Document titles are English source names,
passed through unchanged (consistent with the translate-bridge design — products
/citations stay English). `aria-live="polite"` on the caption for screen
readers; the existing `role="status"` tractor wrapper is retained.

### `constants/i18n.js`

New keys (EN + ES): `progressSearching`, `progressFoundSources`
(`"Found {n} sources"` / `"{n} fuentes encontradas"`), `progressWriting`,
`progressVerifying`.

## Error / cancellation

- Real generation error → `rag_task.result()` raises → existing error frame + `[DONE]`.
- Client/proxy disconnect → `CancelledError` → `rag_task.cancel()` (existing).
- Provider quota fallback inside generation → `writing` already emitted once
  before the loop; fallback is invisible to progress.
- Malformed progress payload → consumer skips (existing malformed guard).

## Offline / PWA

Unaffected. Offline never streams (no network); the OfflineSafetyStub path does
not touch `event_stream`.

## Testing (TDD)

**Backend**
- `run_rag_query` with a provided queue puts the 4 stages in order with correct
  payloads (`sources_found` carries `count` + `titles`); mock retrieval/LLM/guard.
- `event_stream`: yields progress frames in stage order, then the advisory frame,
  then `[DONE]`. Keepalive still emitted when a stage stalls past the interval
  (mock a slow stage). Error path still emits one error frame + `[DONE]`.

**Frontend**
- `useSSEQuery.test.js`: progress frame → `onProgress`; advisory → `onResult`;
  `delivered === false` for a progress-only stream (retry surfaces); no throw on
  a progress frame with missing `count`/`titles`.
- `QueryProgress` render test: each stage → correct localized caption (EN + ES);
  `sources_found` renders the titles; `stage == null` renders the default caption.

**E2E (Playwright)**
- Mocked SSE emitting `searching → sources_found → writing → verifying → advisory`
  asserts the stepper caption transitions then the advisory card renders and the
  progress element is gone.

## Files touched

- `backend/services/rag.py` — `progress` param + 4 `_emit` calls
- `backend/routers/query.py` — queue drain loop
- `frontend/src/hooks/useSSEQuery.js` — `onProgress` route
- `frontend/src/pages/ChatPage.jsx` — `progressStage` state + wiring
- `frontend/src/components/chat/ChatHistory.jsx` — render `QueryProgress`
- `frontend/src/components/chat/QueryProgress.jsx` — NEW (folds in `TypingIndicator`)
- `frontend/src/constants/i18n.js` — 4 new bilingual keys
- Tests across backend + frontend + e2e
```

## Verification

Re-run `python -m scripts.latency_probe` after build: SERIAL unchanged
(confirms no regression). Manual: first progress frame visible < 0.5s; advisory
still gated behind the guard. The probe is the before/after gauge for lever 2/3.
