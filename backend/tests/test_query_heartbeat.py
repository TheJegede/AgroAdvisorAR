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
