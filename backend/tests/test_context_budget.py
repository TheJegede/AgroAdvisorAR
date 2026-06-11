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
