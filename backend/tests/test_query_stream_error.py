# backend/tests/test_query_stream_error.py
"""F10 — the SSE error frame must not leak raw exception text to the client."""
import asyncio
import importlib
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _collect(stream_response):
    async def _run():
        return [chunk async for chunk in stream_response.body_iterator]
    return asyncio.run(_run())


def test_stream_error_is_generic(monkeypatch):
    q = importlib.import_module("routers.query")

    SECRET = "boom postgres://user:pass@host/db key=sk-leak"

    async def fake_classify(*a, **k):
        return "IN_SCOPE_RICE:DIAG"

    async def fake_rag(*a, **k):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(q, "classify_query", fake_classify)
    monkeypatch.setattr(q, "run_rag_query", fake_rag)
    monkeypatch.setattr(q, "get_profile", lambda sub: {"county_fips": "05001"})
    monkeypatch.setattr(q, "rate_limit_hit", lambda *a, **k: (True, 19))
    monkeypatch.setattr(q, "sanitize", lambda m: m)

    req = q.QueryRequest(message="why is my rice yellowing?", language="en")
    resp = asyncio.run(q.query(req, user={"sub": "user-1"}))
    frames = _collect(resp)

    blob = "".join(
        c.decode() if isinstance(c, (bytes, bytearray)) else c for c in frames
    )
    assert q.GENERIC_STREAM_ERROR in blob
    assert "postgres://" not in blob
    assert "sk-leak" not in blob
    # error frame is valid JSON carrying only the generic message
    data_line = next(l for l in blob.splitlines() if l.startswith("data:") and "error" in l)
    payload = json.loads(data_line[len("data:"):].strip())
    assert payload == {"error": q.GENERIC_STREAM_ERROR}
