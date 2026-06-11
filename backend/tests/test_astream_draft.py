"""Tests for rag._astream_draft — token-streaming helper."""
import asyncio
import importlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.messages import AIMessageChunk


# ---------------------------------------------------------------------------
# Fake streaming infrastructure
# ---------------------------------------------------------------------------

class FakeStreamingLLM:
    """Fake LLM that yields pre-canned string chunks as AIMessageChunks."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def astream(self, messages, config=None):
        for c in self._chunks:
            yield AIMessageChunk(content=c)

    def __or__(self, other):
        return _FakeChain(self, other)


class _FakeChain:
    """Composition of FakeStreamingLLM | parser — supports `.astream()`."""

    def __init__(self, llm, parser):
        self._llm = llm
        self._parser = parser

    async def astream(self, messages, config=None):
        async def _gen():
            async for chunk in self._llm.astream(messages, config=config):
                yield chunk

        async for item in self._parser.atransform(_gen(), config=config):
            yield item


# ---------------------------------------------------------------------------
# Test 1: partial callbacks and final dict
# ---------------------------------------------------------------------------

def test_astream_draft_yields_partials_and_returns_final():
    """Fake LLM that streams JSON token chunks yields ≥2 callbacks and
    returns a final dict with the expected key."""
    rag = importlib.import_module("services.rag")
    _astream_draft = rag._astream_draft

    chunks = [
        '{"problem_summary": "rice blast", "recomm',
        'ended_actions": ["apply fungicide"]',
        ', "confidence": "High"}',
    ]
    llm = FakeStreamingLLM(chunks)
    partials_received = []

    async def on_partial(d):
        partials_received.append(d)

    async def _run():
        return await _astream_draft(llm, [], run_config=None, on_partial=on_partial)

    result = asyncio.run(_run())

    assert len(partials_received) >= 2, (
        f"Expected ≥2 on_partial calls, got {len(partials_received)}"
    )
    assert result is not None
    assert result.get("problem_summary") == "rice blast"


# ---------------------------------------------------------------------------
# Test 2: empty dict must NOT trigger on_partial
# ---------------------------------------------------------------------------

def test_astream_draft_skips_empty_dict():
    """on_partial must never be called with an empty dict {}.

    JsonOutputParser emits partial dicts as it accumulates tokens.  When given
    token-by-token chunks of a single JSON object it first emits {} (no fields
    yet), then the fully-built dict once all tokens arrive.  Only the non-empty
    dict must reach on_partial.
    """
    rag = importlib.import_module("services.rag")
    _astream_draft = rag._astream_draft

    # Incremental tokens of ONE JSON object — parser yields {} first, then
    # the full dict.  The empty intermediate {} must be filtered out.
    chunks = ["{", '"problem_summary"', ': "ok"', "}"]
    llm = FakeStreamingLLM(chunks)
    partials_received = []

    async def on_partial(d):
        partials_received.append(d)

    async def _run():
        return await _astream_draft(llm, [], run_config=None, on_partial=on_partial)

    result = asyncio.run(_run())

    # Empty dict must never have been passed to on_partial
    for p in partials_received:
        assert p, f"on_partial was called with falsy value: {p!r}"

    # The non-empty dict should have been forwarded
    assert any(p.get("problem_summary") == "ok" for p in partials_received)
    assert result is not None
    assert result.get("problem_summary") == "ok"


# ---------------------------------------------------------------------------
# Test 3: no valid JSON → returns None, on_partial never called
# ---------------------------------------------------------------------------

def test_astream_draft_returns_none_on_empty_stream():
    """A LLM that yields only empty/invalid JSON should return None without
    ever calling on_partial."""
    rag = importlib.import_module("services.rag")
    _astream_draft = rag._astream_draft

    chunks = [""]  # empty string — no valid JSON
    llm = FakeStreamingLLM(chunks)
    partials_received = []

    async def on_partial(d):
        partials_received.append(d)

    async def _run():
        return await _astream_draft(llm, [], run_config=None, on_partial=on_partial)

    result = asyncio.run(_run())

    assert result is None, f"Expected None, got {result!r}"
    assert partials_received == [], (
        f"on_partial should not have been called, got: {partials_received}"
    )
