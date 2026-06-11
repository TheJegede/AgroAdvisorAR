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
