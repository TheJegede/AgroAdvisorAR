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
