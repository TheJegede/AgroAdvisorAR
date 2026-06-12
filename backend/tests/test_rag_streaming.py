"""Tests for token-streaming path in run_rag_query (Task 2).

Covers:
  - stream=True pushes ≥1 {"kind": "partial", ...} items onto the progress queue
  - stream=False produces zero partial items but returns a valid advisory
  - astream failure during streaming falls back to ainvoke with zero partial items
"""
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.messages import AIMessageChunk

from services import rag


# ---------------------------------------------------------------------------
# Fake streaming infrastructure (mirrored from test_astream_draft.py)
# ---------------------------------------------------------------------------

class FakeStreamingLLM:
    """Fake LLM that yields pre-canned string chunks as AIMessageChunks.

    Also supports with_structured_output() so it can serve as an ainvoke
    fallback provider in the non-streaming path.
    """

    def __init__(self, chunks, ainvoke_result=None):
        self._chunks = chunks
        self._ainvoke_result = ainvoke_result  # returned by _Structured.ainvoke

    async def astream(self, messages, config=None):
        for c in self._chunks:
            yield AIMessageChunk(content=c)

    def __or__(self, other):
        return _FakeChain(self, other)

    def with_structured_output(self, schema, **kw):
        return _Structured(self._ainvoke_result)


class _FakeChain:
    """Composition of FakeStreamingLLM | parser — supports .astream()."""

    def __init__(self, llm, parser):
        self._llm = llm
        self._parser = parser

    async def astream(self, messages, config=None):
        async def _gen():
            async for chunk in self._llm.astream(messages, config=config):
                yield chunk

        async for item in self._parser.atransform(_gen(), config=config):
            yield item


class _Structured:
    """Returned by with_structured_output; mimics a bound runnable's ainvoke."""

    def __init__(self, result):
        self._result = result

    async def ainvoke(self, messages, config=None):
        return self._result


class FakeStreamingLLMWithFailure:
    """Fake LLM whose astream raises but whose ainvoke fallback works."""

    def __init__(self, ainvoke_result):
        self._ainvoke_result = ainvoke_result

    async def astream(self, messages, config=None):
        raise Exception("astream failed")
        # Make this a proper async generator so __or__ chain works
        yield  # pragma: no cover

    def __or__(self, other):
        return _FakeFailChain(self, other)

    def with_structured_output(self, schema, **kw):
        return _Structured(self._ainvoke_result)


class _FakeFailChain:
    """Chain that raises on astream."""

    def __init__(self, llm, parser):
        self._llm = llm
        self._parser = parser

    async def astream(self, messages, config=None):
        raise Exception("astream failed")
        yield  # pragma: no cover


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

class _Doc:
    def __init__(self, title="Rice Disease MP154", text="some text"):
        self.metadata = {"document_title": title, "section_heading": "Sec"}
        self.page_content = text


def _make_advisory_response(county_fips="05055"):
    from models.advisory import AdvisoryResponse, ContextMeta
    return AdvisoryResponse(
        problem_summary="ok",
        likely_causes=[],
        recommended_actions=[],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="High",
        confidence_explanation="x",
        language="en",
        context_meta=ContextMeta(
            soil_data_available=False,
            weather_data_available=False,
            county_fips=county_fips,
        ),
    )


def _make_advisory_draft(county_fips="05055"):
    from models.advisory import AdvisoryDraft, ContextMeta
    return AdvisoryDraft(
        problem_summary="ok",
        likely_causes=[],
        recommended_actions=[],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="High",
        confidence_explanation="x",
        language="en",
        context_meta=ContextMeta(
            soil_data_available=False,
            weather_data_available=False,
            county_fips=county_fips,
        ),
    )


def _patch_externals(monkeypatch, llm, county_fips="05055"):
    """Patch all external dependencies of run_rag_query."""
    docs = [_Doc()]

    monkeypatch.setattr(rag, "_get_vectorstore", lambda: object())
    monkeypatch.setattr(rag, "_fanout_search", lambda vs, m, k, ns: docs)

    async def fake_context(fips):
        return {"soil": {"available": False}, "weather": {"available": False}}
    monkeypatch.setattr(rag, "get_context", fake_context)

    monkeypatch.setattr(rag, "_get_groq_llm", lambda: llm)
    monkeypatch.setattr(rag, "_get_deepinfra_llm", lambda: None)
    monkeypatch.setattr(rag, "_get_groq_fast_llm", lambda: None)
    monkeypatch.setattr(rag, "_get_llm", lambda: None)

    async def fake_post(result, docs, soil, weather, county_fips, run_config=None, category=None):
        return _make_advisory_response(county_fips)
    monkeypatch.setattr(rag, "_postprocess_async", fake_post)

    # Ensure LLM_PRIMARY is not "local" so ordered includes our fake groq LLM
    import config as cfg
    monkeypatch.setattr(cfg, "LLM_PRIMARY", "groq")


# ---------------------------------------------------------------------------
# Test 1: stream=True pushes ≥1 partial queue item before returning advisory
# ---------------------------------------------------------------------------

def test_stream_true_pushes_partial_items(monkeypatch):
    """stream=True causes ≥1 {"kind": "partial", ...} to be pushed onto the queue."""
    # Build a valid AdvisoryDraft JSON split across 3 chunks
    draft_json = (
        '{"problem_summary": "rice blast", '
        '"confidence": "High", '
        '"confidence_explanation": "verified", '
        '"language": "en", '
        '"context_meta": {"soil_data_available": false, '
        '"weather_data_available": false, "county_fips": "05055"}, '
        '"likely_causes": [], "recommended_actions": [], '
        '"products_rates": [], "warnings": [], "citations": []}'
    )
    # Split into 3 chunks
    third = len(draft_json) // 3
    chunks = [draft_json[:third], draft_json[third:2*third], draft_json[2*third:]]

    llm = FakeStreamingLLM(chunks, ainvoke_result=_make_advisory_draft())
    _patch_externals(monkeypatch, llm)

    async def _run():
        q = asyncio.Queue()
        advisory, retrieved = await rag.run_rag_query(
            message="soybean seeding rate",
            county_fips="05055",
            language="en",
            category="IN_SCOPE_SOYBEANS:INFO",
            session_history=[],
            progress=q,
            stream=True,
        )
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        return advisory, items

    advisory, items = asyncio.run(_run())

    partial_items = [i for i in items if i.get("kind") == "partial"]
    assert len(partial_items) >= 1, (
        f"Expected ≥1 partial items, got {len(partial_items)}. All items: {items}"
    )
    assert advisory is not None
    assert advisory.problem_summary == "ok"  # from fake_post


def test_partial_frames_throttled(monkeypatch):
    """F7: many partials arriving inside one throttle window collapse to a single
    frame (the cumulative draft is not re-sent per token)."""
    draft_json = (
        '{"problem_summary": "rice blast", '
        '"confidence": "High", '
        '"confidence_explanation": "verified", '
        '"language": "en", '
        '"context_meta": {"soil_data_available": false, '
        '"weather_data_available": false, "county_fips": "05055"}, '
        '"likely_causes": [], "recommended_actions": [], '
        '"products_rates": [], "warnings": [], "citations": []}'
    )
    size = max(1, len(draft_json) // 12)
    chunks = [draft_json[i:i + size] for i in range(0, len(draft_json), size)]

    llm = FakeStreamingLLM(chunks, ainvoke_result=_make_advisory_draft())
    _patch_externals(monkeypatch, llm)
    # Huge window -> every partial after the first is throttled away.
    monkeypatch.setattr(rag, "PARTIAL_STREAM_THROTTLE_SECONDS", 100.0)

    async def _run():
        q = asyncio.Queue()
        await rag.run_rag_query(
            message="soybean seeding rate",
            county_fips="05055",
            language="en",
            category="IN_SCOPE_SOYBEANS:INFO",
            session_history=[],
            progress=q,
            stream=True,
        )
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        return items

    items = asyncio.run(_run())
    partial_items = [i for i in items if i.get("kind") == "partial"]
    assert len(partial_items) == 1, (
        f"Expected exactly 1 throttled partial, got {len(partial_items)}"
    )


# ---------------------------------------------------------------------------
# Test 2: stream=False produces zero partial items
# ---------------------------------------------------------------------------

def test_stream_false_produces_no_partial_items(monkeypatch):
    """stream=False must not push any {"kind": "partial"} items."""
    llm = FakeStreamingLLM([], ainvoke_result=_make_advisory_draft())
    _patch_externals(monkeypatch, llm)

    async def _run():
        q = asyncio.Queue()
        advisory, retrieved = await rag.run_rag_query(
            message="soybean seeding rate",
            county_fips="05055",
            language="en",
            category="IN_SCOPE_SOYBEANS:INFO",
            session_history=[],
            progress=q,
            stream=False,
        )
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        return advisory, items

    advisory, items = asyncio.run(_run())

    partial_items = [i for i in items if i.get("kind") == "partial"]
    assert partial_items == [], (
        f"Expected zero partial items with stream=False, got {partial_items}"
    )
    assert advisory is not None


# ---------------------------------------------------------------------------
# Test 3: astream failure falls back to ainvoke — zero partial items, valid result
# ---------------------------------------------------------------------------

def test_stream_astream_failure_falls_back_to_ainvoke(monkeypatch):
    """When astream raises, run_rag_query falls back to ainvoke with zero partials."""
    llm = FakeStreamingLLMWithFailure(ainvoke_result=_make_advisory_draft())
    _patch_externals(monkeypatch, llm)

    async def _run():
        q = asyncio.Queue()
        advisory, retrieved = await rag.run_rag_query(
            message="soybean seeding rate",
            county_fips="05055",
            language="en",
            category="IN_SCOPE_SOYBEANS:INFO",
            session_history=[],
            progress=q,
            stream=True,
        )
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        return advisory, items

    advisory, items = asyncio.run(_run())

    partial_items = [i for i in items if i.get("kind") == "partial"]
    assert partial_items == [], (
        f"Expected zero partial items after astream failure, got {partial_items}"
    )
    assert advisory is not None, "Advisory must still be returned after fallback"
