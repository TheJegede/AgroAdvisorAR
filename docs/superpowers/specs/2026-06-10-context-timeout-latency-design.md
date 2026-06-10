# Bounded Context Fetch (Latency Lever 4)

**Date:** 2026-06-10
**Status:** Design approved, pending spec review
**Lever:** Answer-latency lever 4 (cache-miss stall; no warm-up).

## Problem

`run_rag_query` awaits the SSURGO+NOAA context before building the prompt
(`rag.py:361` `ctx = await context_task`). Context runs concurrently with
retrieval and is 6h-cached, so it is normally off the critical path — BUT on a
cache MISS (first query per county, cache expiry, or Redis down) it blocks
generation.

`fetch_noaa` (`context.py:93`) makes **two sequential** weather.gov GETs
(gridpoint resolve → forecast), each with `timeout=3.0` → up to ~6s worst case.
The latency probe observed context taking 2–4s with a `weather.gov` ReadTimeout.
When it stalls, generation waits for it.

The cold-classify ~1.3s first-query penalty is explicitly **not** addressed here
(owner chose no warm-up; lever 1's progress frame masks it, zero extra quota).

## Goal & non-goals

**Goal:** context fetch can never stall the critical path beyond a fixed budget;
degrade to "unavailable" (the already-handled state) instead of hanging.

**Non-goals (YAGNI):** no startup warm-up ping; no change to caching, the
context payload shape, or the prompt builder's unavailable handling.

## Approach

Two bounds, defense in depth:

1. **Tighter per-call timeout.** `fetch_noaa` httpx client `timeout=3.0 → 1.5`
   (2 sequential GETs → ~3s worst, not ~6s). Apply the same `1.5s` bound to
   `fetch_ssurgo`'s client.

2. **Overall budget at the gather.** Wrap `get_context`'s `asyncio.gather` in
   `asyncio.wait_for(timeout=config.CONTEXT_BUDGET_SECONDS)` (default `2.5`):

```python
async def get_context(fips: str) -> dict:
    try:
        soil, weather = await asyncio.wait_for(
            asyncio.gather(fetch_ssurgo(fips), fetch_noaa(fips)),
            timeout=config.CONTEXT_BUDGET_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("context budget exceeded for fips %s; degrading to unavailable", fips)
        soil, weather = _unavailable(), _unavailable()
    return {"soil": soil, "weather": weather}
```

`_unavailable()` is the existing degraded shape (`{"available": False, ...}`);
downstream (`_postprocess_async` context_meta, prompt builder) already handles
it. The budget (2.5s) sits comfortably above the warm/cached path (~0.1s) so a
cache HIT never trips it, and below the ~6s stall.

A cache MISS now costs ≤2.5s for context (overlapped with retrieval), and on a
hard upstream hang the pipeline proceeds with soil/weather unavailable rather
than blocking generation.

## Config

- `config.CONTEXT_BUDGET_SECONDS` (env `CONTEXT_BUDGET_SECONDS`, default `2.5`).
- NOAA/SSURGO per-call timeout `1.5` (constant; env-override optional).

## Testing (TDD)

- `get_context` returns both-unavailable when the gather exceeds the budget
  (monkeypatch `fetch_ssurgo`/`fetch_noaa` to `await asyncio.sleep(5)`); asserts
  it returns within ~budget, not 5s.
- Cache-HIT / fast path: fetches returning immediately are unaffected — budget
  not tripped, real soil/weather returned.
- `fetch_noaa` uses the 1.5s client timeout (assert client construction arg).
- Degraded context still yields a valid advisory (existing unavailable handling
  regression).

## Files touched

- `backend/services/context.py` — NOAA/SSURGO timeout 1.5s, `get_context`
  `wait_for` budget
- `backend/config.py` — `CONTEXT_BUDGET_SECONDS`
- `backend/tests/test_context*.py` — budget + timeout tests

## Verification

`scripts/latency_probe.py` `context` column bounded ≤ ~2.5s on a cold cache
(was 2–4s+); SERIAL no longer spikes when weather.gov is slow. Warm/cached runs
unchanged.
