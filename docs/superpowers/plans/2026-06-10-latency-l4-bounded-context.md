# Latency L4 — Bounded Context Fetch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Build order: PLAN 1 of 4** (L4 → L2 → L1 → L3). L4 is first: smallest, lowest-risk, no dependency on the others. Spec: `docs/superpowers/specs/2026-06-10-context-timeout-latency-design.md`.

**Goal:** Ensure SSURGO+NOAA context fetch can never stall the query critical path beyond a fixed budget, degrading to the already-handled "unavailable" state instead of hanging.

**Architecture:** `run_rag_query` awaits `get_context()` before building the prompt (`backend/services/rag.py:361`). On a cache MISS, `fetch_noaa` makes two sequential weather.gov GETs (up to ~6s). Add (1) a tighter per-call httpx timeout and (2) an overall `asyncio.wait_for` budget around the `gather` in `get_context`, returning both-unavailable on breach.

**Tech Stack:** Python, httpx (async), asyncio, pytest (tests use `asyncio.run`, no pytest-asyncio).

---

## Background for an engineer with zero context

- `backend/services/context.py` fetches soil (`fetch_ssurgo`) and weather (`fetch_noaa`) and exposes `get_context(fips)` which `asyncio.gather`s both. Each fetcher is wrapped by `_cached_fetch` (6h Upstash cache) and returns `_unavailable()` = `{"available": False}` on any failure.
- Downstream already handles unavailable: `backend/services/rag.py` `_postprocess_async` stamps `context_meta.soil_data_available`/`weather_data_available` from `.get("available", False)`, and `utils/prompt.build_system_prompt` renders gracefully when context is unavailable. **No downstream change is needed** — degrading to unavailable is safe.
- Config lives in `backend/config.py` (flat module-level constants, env-overridable via `os.environ.get`).
- Tests live in `backend/tests/`, run with `cd backend && pytest tests/<file> -v`. Async code is exercised with `asyncio.run(...)` inside a sync `def test_...`. Every test file starts with the `BACKEND_DIR` sys.path boilerplate (see existing `tests/test_citation_guard_v2.py`).

## File Structure

- Modify: `backend/config.py` — add `CONTEXT_BUDGET_SECONDS`, `CONTEXT_FETCH_TIMEOUT`.
- Modify: `backend/services/context.py` — use `CONTEXT_FETCH_TIMEOUT` in both fetchers; wrap `get_context`'s gather in `asyncio.wait_for(... , CONTEXT_BUDGET_SECONDS)`.
- Create: `backend/tests/test_context_budget.py` — budget + timeout tests.

---

### Task 1: Config constants

**Files:**
- Modify: `backend/config.py` (append after line 57, the `DEFAULT_COUNTY_FIPS` block, near the other timeouts)

- [ ] **Step 1: Add the constants**

In `backend/config.py`, after the `NOAA_USER_AGENT`/`DEFAULT_COUNTY_FIPS` lines, add:

```python
# Context (SSURGO/NOAA) fetch bounds. On a cache MISS the context await blocks
# generation (rag.py awaits get_context before the prompt). Cap per-call httpx
# time AND the overall gather so a slow/​hanging upstream degrades to
# "unavailable" instead of stalling the answer. Budget sits above the cached
# path (~0.1s) and below the ~6s worst case (NOAA = 2 sequential GETs).
CONTEXT_FETCH_TIMEOUT = float(os.environ.get("CONTEXT_FETCH_TIMEOUT", "1.5"))
CONTEXT_BUDGET_SECONDS = float(os.environ.get("CONTEXT_BUDGET_SECONDS", "2.5"))
```

- [ ] **Step 2: Verify it imports**

Run: `cd backend && python -c "import config; print(config.CONTEXT_FETCH_TIMEOUT, config.CONTEXT_BUDGET_SECONDS)"`
Expected: `1.5 2.5`

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "feat(context): add CONTEXT_FETCH_TIMEOUT and CONTEXT_BUDGET_SECONDS config"
```

---

### Task 2: Overall budget on get_context (TDD)

**Files:**
- Test: `backend/tests/test_context_budget.py` (create)
- Modify: `backend/services/context.py` — `get_context` (currently around line 145)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_context_budget.py`:

```python
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config
from services import context


def test_get_context_degrades_when_budget_exceeded(monkeypatch):
    monkeypatch.setattr(config, "CONTEXT_BUDGET_SECONDS", 0.05)

    async def slow_ssurgo(fips):
        await asyncio.sleep(5)
        return {"available": True}

    async def slow_noaa(fips):
        await asyncio.sleep(5)
        return {"available": True}

    monkeypatch.setattr(context, "fetch_ssurgo", slow_ssurgo)
    monkeypatch.setattr(context, "fetch_noaa", slow_noaa)

    async def _run():
        start = asyncio.get_event_loop().time()
        ctx = await context.get_context("05055")
        elapsed = asyncio.get_event_loop().time() - start
        return ctx, elapsed

    ctx, elapsed = asyncio.run(_run())
    assert ctx["soil"] == {"available": False}
    assert ctx["weather"] == {"available": False}
    assert elapsed < 1.0  # returned at ~budget, not 5s


def test_get_context_returns_real_data_within_budget(monkeypatch):
    monkeypatch.setattr(config, "CONTEXT_BUDGET_SECONDS", 2.5)

    async def fast_ssurgo(fips):
        return {"available": True, "ph": 6.1}

    async def fast_noaa(fips):
        return {"available": True, "forecast_7day": []}

    monkeypatch.setattr(context, "fetch_ssurgo", fast_ssurgo)
    monkeypatch.setattr(context, "fetch_noaa", fast_noaa)

    ctx = asyncio.run(context.get_context("05055"))
    assert ctx["soil"]["available"] is True
    assert ctx["weather"]["available"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_context_budget.py -v`
Expected: `test_get_context_degrades_when_budget_exceeded` FAILS — currently `get_context` awaits the gather with no timeout, so it would wait ~5s (test times out / elapsed assertion fails).

- [ ] **Step 3: Implement the budget**

In `backend/services/context.py`, replace the body of `get_context` with:

```python
async def get_context(fips: str) -> dict:
    """Fetch SSURGO + NOAA concurrently, bounded by CONTEXT_BUDGET_SECONDS.

    On a cache MISS this await blocks generation (rag.py awaits it before the
    prompt). If the gather exceeds the budget, degrade BOTH to unavailable
    rather than stall the answer; the 6h cache refills on a later query.
    """
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

(Keep the rest of the file unchanged. `asyncio`, `logger`, `_unavailable`, `fetch_ssurgo`, `fetch_noaa`, and `config` are already imported/defined.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_context_budget.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/context.py backend/tests/test_context_budget.py
git commit -m "feat(context): bound get_context with an overall fetch budget"
```

---

### Task 3: Tighten per-call httpx timeouts (TDD)

**Files:**
- Test: `backend/tests/test_context_budget.py` (extend)
- Modify: `backend/services/context.py` — `fetch_ssurgo` (line ~61) and `fetch_noaa` (line ~102)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_context_budget.py`:

```python
def test_fetchers_use_config_fetch_timeout(monkeypatch):
    monkeypatch.setattr(config, "CONTEXT_FETCH_TIMEOUT", 1.5)
    captured = {}

    real_client = context.httpx.AsyncClient

    def spy_client(*args, **kwargs):
        captured.setdefault("timeouts", []).append(kwargs.get("timeout"))
        return real_client(*args, **kwargs)

    monkeypatch.setattr(context.httpx, "AsyncClient", spy_client)

    # Force a cache miss and a quick network failure so the fetcher constructs a
    # client then returns unavailable. county 05055 is valid; the URL will be hit
    # but we only assert on the timeout passed to AsyncClient.
    monkeypatch.setattr(context, "cache_get", lambda k: None)
    monkeypatch.setattr(context, "cache_set", lambda *a, **k: None)

    asyncio.run(context.fetch_ssurgo("05055"))
    asyncio.run(context.fetch_noaa("05055"))

    assert captured["timeouts"], "AsyncClient was never constructed"
    assert all(t == 1.5 for t in captured["timeouts"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_context_budget.py::test_fetchers_use_config_fetch_timeout -v`
Expected: FAIL — fetchers currently hard-code `timeout=3.0`, so the captured timeouts are `3.0`, not `1.5`.

- [ ] **Step 3: Replace hard-coded timeouts**

In `backend/services/context.py`:
- In `fetch_ssurgo._fetch`, change `async with httpx.AsyncClient(timeout=3.0) as client:` to:
  ```python
  async with httpx.AsyncClient(timeout=config.CONTEXT_FETCH_TIMEOUT) as client:
  ```
- In `fetch_noaa._fetch`, change:
  ```python
  async with httpx.AsyncClient(
      timeout=3.0,
      headers={"User-Agent": config.NOAA_USER_AGENT},
  ) as client:
  ```
  to:
  ```python
  async with httpx.AsyncClient(
      timeout=config.CONTEXT_FETCH_TIMEOUT,
      headers={"User-Agent": config.NOAA_USER_AGENT},
  ) as client:
  ```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_context_budget.py -v`
Expected: all PASS (network calls may fail internally and return unavailable — that is fine; the test only inspects the timeout arg).

- [ ] **Step 5: Commit**

```bash
git add backend/services/context.py backend/tests/test_context_budget.py
git commit -m "feat(context): use CONTEXT_FETCH_TIMEOUT for SSURGO/NOAA clients"
```

---

### Task 4: Regression — full context suite + degraded-context advisory

**Files:**
- Run existing suites that touch context/query.

- [ ] **Step 1: Run the broader suite**

Run: `cd backend && pytest tests/ -k "context or query or rag" -v`
Expected: PASS. If a pre-existing context test hard-asserts a `3.0` timeout, update it to `config.CONTEXT_FETCH_TIMEOUT` (none expected at the time of writing).

- [ ] **Step 2: Manual latency check (optional, needs repo-root `.env` + network)**

Run: `cd backend && python -m scripts.latency_probe`
Expected: the `context` column is bounded at ≤ ~2.5s even on a cold cache (previously 2–4s+ with a weather.gov ReadTimeout). `SERIAL` no longer spikes when weather.gov is slow.

- [ ] **Step 3: Commit (if any test was updated)**

```bash
git add -A
git commit -m "test(context): align context tests with bounded-fetch config"
```

---

## Self-Review (completed)

- **Spec coverage:** per-call timeout 3.0→1.5 (Task 3) ✓; overall `wait_for` budget (Task 2) ✓; degrade-to-unavailable (Task 2) ✓; config keys (Task 1) ✓; no warm-up (out of scope, none added) ✓; tests for budget + timeout + degraded advisory (Tasks 2–4) ✓.
- **Placeholders:** none.
- **Type consistency:** `CONTEXT_FETCH_TIMEOUT`/`CONTEXT_BUDGET_SECONDS` used consistently across config + context; `get_context` returns the same `{"soil":..., "weather":...}` shape as before.
