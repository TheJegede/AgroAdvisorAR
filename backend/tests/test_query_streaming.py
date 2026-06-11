"""Tests for EN-gated partial SSE frame forwarding (Task 3 — token streaming)."""
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
    suppressed = False

    def model_dump(self):
        return {"problem_summary": "ok", "suppressed": False}


def _patch_common(q, monkeypatch, fake_rag):
    async def fake_classify(*a, **k):
        return "IN_SCOPE_RICE:DIAG"
    monkeypatch.setattr(q, "classify_query", fake_classify)
    monkeypatch.setattr(q, "run_rag_query", fake_rag)
    monkeypatch.setattr(q, "get_profile", lambda sub: {"county_fips": "05001"})
    monkeypatch.setattr(q, "rate_limit_hit", lambda *a, **k: (True, 19))
    monkeypatch.setattr(q, "sanitize", lambda m: m)


def _patch_cache_miss(q, monkeypatch):
    """Patch answer_cache to simulate a first-turn EN cache miss."""
    monkeypatch.setattr(q.answer_cache, "answer_cache_key", lambda *a, **k: "test-key")
    monkeypatch.setattr(q.answer_cache, "get_cached_answer", lambda k: None)
    monkeypatch.setattr(q.answer_cache, "set_cached_answer", lambda *a, **k: None)
    monkeypatch.setattr(q.answer_cache, "is_cacheable_as_reference", lambda d: False)


def test_en_first_turn_emits_partial_frames_before_advisory(monkeypatch):
    """EN first-turn query (cache miss) must emit >=1 partial frame before advisory."""
    q = importlib.import_module("routers.query")

    async def fake_rag(*a, progress=None, **k):
        await progress.put({"kind": "partial", "draft": {"problem_summary": "partial"}})
        await progress.put({"stage": "verifying"})
        return (_FakeResult(), [])

    _patch_common(q, monkeypatch, fake_rag)
    _patch_cache_miss(q, monkeypatch)

    req = q.QueryRequest(message="why is my rice yellow?", language="en", session_history=[])
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))
    blob = _blob(_collect(resp))

    assert '"partial"' in blob, "Expected at least one partial frame in SSE output"
    i_partial = blob.index('"partial"')
    i_advisory = blob.index('"advisory"')
    assert i_partial < i_advisory, "partial frame must appear before advisory frame"
    assert "[DONE]" in blob


def test_es_query_emits_no_partial_frames(monkeypatch):
    """ES queries must not emit partial frames (draft would be in English pre-translation).

    The router passes stream=False for ES queries; real run_rag_query won't enqueue
    partial items when stream=False. The fake_rag here respects the stream kwarg to
    mirror that contract.
    """
    q = importlib.import_module("routers.query")

    async def fake_rag(*a, progress=None, stream=False, **k):
        # Only put partial items when stream=True — mirrors real run_rag_query behaviour.
        if stream:
            await progress.put({"kind": "partial", "draft": {"problem_summary": "partial"}})
        await progress.put({"stage": "verifying"})
        return (_FakeResult(), [])

    _patch_common(q, monkeypatch, fake_rag)
    _patch_cache_miss(q, monkeypatch)

    # Stub the ES translation path so the test doesn't need real Gemini/Groq.
    async def _passthrough(msg, lang, user_id=None):
        return msg
    async def _passthrough_adv(adv, user_id=None):
        return adv
    monkeypatch.setattr(q, "maybe_translate_query", _passthrough)
    monkeypatch.setattr(q, "translate_advisory_to_es", _passthrough_adv)

    req = q.QueryRequest(message="por que el arroz esta amarillo?", language="es", session_history=[])
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))
    blob = _blob(_collect(resp))

    assert '"partial"' not in blob, "ES query must not emit any partial frames"
    assert '"advisory"' in blob, "ES query must still emit the advisory frame"
    assert "[DONE]" in blob


def test_followup_query_emits_no_partial_frames(monkeypatch):
    """Follow-up queries (session_history non-empty → cache_key=None) must not stream partials.

    The router passes stream=False when cache_key is None; real run_rag_query won't
    enqueue partial items. The fake respects that contract so the assertion is
    realistic.
    """
    q = importlib.import_module("routers.query")

    async def fake_rag(*a, progress=None, stream=False, **k):
        # Respect stream flag — mirrors real run_rag_query behaviour.
        if stream:
            await progress.put({"kind": "partial", "draft": {"problem_summary": "partial"}})
        await progress.put({"stage": "verifying"})
        return (_FakeResult(), [])

    _patch_common(q, monkeypatch, fake_rag)
    # Do NOT patch answer_cache_key — session_history is non-empty so the cache
    # block is skipped entirely and cache_key stays None.

    req = q.QueryRequest(
        message="what about potassium?",
        language="en",
        session_history=[{"role": "user", "content": "prev question"}],
    )
    resp = asyncio.run(q.query(req, user={"sub": "u1"}))
    blob = _blob(_collect(resp))

    assert '"partial"' not in blob, "Follow-up query must not emit any partial frames"
    assert '"advisory"' in blob, "Follow-up query must still emit the advisory frame"
    assert "[DONE]" in blob
