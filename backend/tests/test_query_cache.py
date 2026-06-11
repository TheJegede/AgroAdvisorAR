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


def _patch_base(q, monkeypatch):
    async def fake_classify(*a, **k):
        return "IN_SCOPE_SOYBEANS:INFO"
    monkeypatch.setattr(q, "classify_query", fake_classify)
    monkeypatch.setattr(q, "get_profile", lambda sub: {"county_fips": "05055"})
    monkeypatch.setattr(q, "rate_limit_hit", lambda *a, **k: (True, 19))
    monkeypatch.setattr(q, "sanitize", lambda m: m)


def test_cache_hit_skips_rag(monkeypatch):
    q = importlib.import_module("routers.query")
    _patch_base(q, monkeypatch)

    called = {"rag": 0}
    async def fake_rag(*a, **k):
        called["rag"] += 1
        raise AssertionError("run_rag_query must not be called on a cache hit")
    monkeypatch.setattr(q, "run_rag_query", fake_rag)

    cached = {"problem_summary": "Soybeans are a legume.", "_category": "IN_SCOPE_SOYBEANS:INFO"}
    monkeypatch.setattr(q.answer_cache, "get_cached_answer", lambda key: dict(cached))
    monkeypatch.setattr(q, "save_message", lambda *a, **k: {"id": "m1"})

    req = q.QueryRequest(message="soybean facts", language="en")
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))
    blob = _blob(_collect(resp))
    assert called["rag"] == 0
    assert '"problem_summary": "Soybeans are a legume."' in blob
    assert '"_category"' not in blob  # internal field stripped from the frame
    assert "[DONE]" in blob


def test_cache_not_read_with_session_history(monkeypatch):
    q = importlib.import_module("routers.query")
    _patch_base(q, monkeypatch)
    seen = {"get": 0}
    monkeypatch.setattr(q.answer_cache, "get_cached_answer", lambda key: seen.__setitem__("get", seen["get"] + 1) or None)

    class _Res:
        confidence_score = 0.9
        suppressed = False
        escalation = None
        def model_dump(self):
            return {"problem_summary": "x", "response_type": "informational",
                    "products_rates": [], "warnings": [], "suppressed": False}
    async def fake_rag(*a, **k):
        return (_Res(), [])
    monkeypatch.setattr(q, "run_rag_query", fake_rag)
    monkeypatch.setattr(q, "save_message", lambda *a, **k: {"id": "m1"})

    req = q.QueryRequest(message="soybean facts", language="en",
                         session_history=[{"role": "user", "content": "hi"},
                                          {"role": "assistant", "content": "hello"}])
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))
    _blob(_collect(resp))
    assert seen["get"] == 0  # never read the cache on a follow-up
