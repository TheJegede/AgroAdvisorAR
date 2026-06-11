import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import rag


def test_emit_puts_when_queue_present():
    async def _run():
        q = asyncio.Queue()
        await rag._emit(q, "searching")
        await rag._emit(q, "sources_found", count=3, titles=["A", "B", "C"])
        return [q.get_nowait(), q.get_nowait()]

    items = asyncio.run(_run())
    assert items[0] == {"stage": "searching"}
    assert items[1] == {"stage": "sources_found", "count": 3, "titles": ["A", "B", "C"]}


def test_emit_noop_when_queue_none():
    async def _run():
        await rag._emit(None, "searching")  # must not raise
        return True
    assert asyncio.run(_run()) is True


class _Doc:
    def __init__(self, title, text):
        self.metadata = {"document_title": title, "section_heading": "Sec"}
        self.page_content = text


def test_run_rag_query_emits_four_stages_in_order(monkeypatch):
    q = asyncio.Queue()
    docs = [_Doc("Rice Disease MP154", "text one"), _Doc("", "text two")]

    monkeypatch.setattr(rag, "_get_vectorstore", lambda: object())
    monkeypatch.setattr(rag, "_fanout_search", lambda vs, m, k, ns: docs)

    async def fake_context(fips):
        return {"soil": {"available": False}, "weather": {"available": False}}
    monkeypatch.setattr(rag, "get_context", fake_context)

    class _Structured:
        async def ainvoke(self, messages, config=None):
            return object()  # _postprocess_async is patched, shape irrelevant

    class _LLM:
        def with_structured_output(self, schema, **kw):
            return _Structured()

    monkeypatch.setattr(rag, "_get_groq_llm", lambda: _LLM())
    monkeypatch.setattr(rag, "_get_deepinfra_llm", lambda: None)
    monkeypatch.setattr(rag, "_get_groq_fast_llm", lambda: None)
    monkeypatch.setattr(rag, "_get_llm", lambda: None)

    async def fake_post(result, docs, soil, weather, county_fips, run_config=None, category=None):
        from models.advisory import AdvisoryResponse, ContextMeta
        return AdvisoryResponse(
            problem_summary="ok", likely_causes=[], recommended_actions=[],
            products_rates=[], warnings=[], citations=[], confidence="High",
            confidence_explanation="x", language="en",
            context_meta=ContextMeta(soil_data_available=False, weather_data_available=False, county_fips=county_fips),
        )
    monkeypatch.setattr(rag, "_postprocess_async", fake_post)

    async def _run():
        await rag.run_rag_query(
            message="soybean seeding rate", county_fips="05055", language="en",
            category="IN_SCOPE_SOYBEANS:INFO", session_history=[], progress=q,
        )
        out = []
        while not q.empty():
            out.append(q.get_nowait())
        return out

    stages = asyncio.run(_run())
    names = [s["stage"] for s in stages]
    assert names == ["searching", "sources_found", "writing", "verifying"]
    sf = next(s for s in stages if s["stage"] == "sources_found")
    assert sf["count"] == 2
    assert sf["titles"] == ["Rice Disease MP154", "Source 2"]  # titleless -> fallback

