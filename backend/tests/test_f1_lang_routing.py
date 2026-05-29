import sys
from pathlib import Path
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_bge_embeddings_produces_1024_dim(monkeypatch):
    """BGEEmbeddings.embed_query must return a list of 1024 floats."""
    import numpy as np

    fake_vec = np.zeros(1024, dtype="float32")

    class FakeModel:
        def encode(self, texts, normalize_embeddings=True):
            if isinstance(texts, list):
                return np.stack([fake_vec] * len(texts))
            return fake_vec

    import services.embedding as emb_mod
    monkeypatch.setattr(emb_mod, "_multilingual_model", FakeModel())

    from services.embedding import BGEEmbeddings
    bge = BGEEmbeddings()
    result = bge.embed_query("¿Cómo controlo el acaro del arroz?")
    assert len(result) == 1024
    assert all(isinstance(v, float) for v in result)


def test_detect_language_spanish():
    from services.classifier import detect_language
    assert detect_language("¿Cómo controlo el acaro del arroz en Arkansas?") == "es"


def test_detect_language_english():
    from services.classifier import detect_language
    assert detect_language("How do I control blast disease in rice?") == "en"


def test_detect_language_empty_defaults_en():
    from services.classifier import detect_language
    assert detect_language("") == "en"


def test_detect_language_short_text_defaults_en():
    from services.classifier import detect_language
    # Very short text raises LangDetectException — must default to 'en'
    assert detect_language("ok") == "en"


def test_run_rag_query_es_uses_multilingual_vectorstore(monkeypatch):
    """detected_lang='es' → similarity_search called on multilingual vectorstore."""
    import asyncio
    import importlib
    from langchain_core.documents import Document

    rag = importlib.import_module("services.rag")
    calls = []

    class FakeVS:
        def __init__(self, name):
            self._name = name

        def similarity_search(self, query, **kwargs):
            calls.append(self._name)
            return [Document(page_content="test chunk", metadata={"document_title": "T"})]

    class FakeLLM:
        def with_structured_output(self, schema):
            return self

        async def ainvoke(self, messages):
            from models.advisory import AdvisoryResponse, ContextMeta
            return AdvisoryResponse(
                problem_summary="test",
                likely_causes=[],
                recommended_actions=[],
                products_rates=[],
                warnings=[],
                confidence="High",
                confidence_explanation="test",
                language="es",
                citations=[],
                context_meta=ContextMeta(
                    soil_data_available=False,
                    weather_data_available=False,
                    county_fips="05001",
                ),
            )

    monkeypatch.setattr(rag, "_vectorstore", FakeVS("en"))
    monkeypatch.setattr(rag, "_vectorstore_es", FakeVS("es"))
    monkeypatch.setattr(rag, "_get_llm", lambda: FakeLLM())

    async def fake_get_context(_fips):
        return {"soil": {}, "weather": {}}

    monkeypatch.setattr(rag, "get_context", fake_get_context)

    import services.citation_guard_v2 as cgv2

    async def fake_verify(answer, chunks):
        return {"confidence_score": 0.9, "claim_verification": []}

    monkeypatch.setattr(cgv2, "verify_answer", fake_verify)

    asyncio.run(rag.run_rag_query(
        message="¿Cómo controlo el acaro en arroz?",
        county_fips="05001",
        language="es",
        category="IN_SCOPE_RICE",
        session_history=[],
        detected_lang="es",
    ))

    assert "es" in calls, f"Expected multilingual vectorstore, got calls={calls}"


def test_query_router_passes_detected_lang_to_rag(monkeypatch):
    """Spanish message → detected_lang='es' forwarded to run_rag_query even if UI lang is 'en'."""
    import asyncio
    import importlib

    query_router = importlib.import_module("routers.query")
    detected_langs_seen = []

    async def fake_classify(_message, **_kwargs):
        return "IN_SCOPE_RICE"

    class FakeResult:
        confidence_score = 0.9
        escalation = None

        def model_dump(self):
            return {"problem_summary": "test"}

    async def fake_run_rag(**kwargs):
        detected_langs_seen.append(kwargs.get("detected_lang"))
        return FakeResult(), []

    monkeypatch.setattr(query_router, "classify_query", fake_classify)
    monkeypatch.setattr(query_router, "run_rag_query", fake_run_rag)
    monkeypatch.setattr(query_router, "save_message", lambda *a, **k: {"id": "x"})
    monkeypatch.setattr(query_router, "get_profile", lambda _: {"county_fips": "05001"})
    monkeypatch.setattr(query_router, "rate_limit_hit", lambda *_: (True, 1))

    req = query_router.QueryRequest(
        message="¿Cómo controlo el acaro del arroz?",
        language="en",  # UI toggle is EN, but message is Spanish
        session_id="s1",
    )
    response = asyncio.run(query_router.query(req, {"sub": "user-id"}))

    async def drain():
        async for _ in response.body_iterator:
            pass

    asyncio.run(drain())

    assert detected_langs_seen == ["es"], f"Expected ['es'], got {detected_langs_seen}"


def test_run_rag_query_en_uses_default_vectorstore(monkeypatch):
    """detected_lang='en' → similarity_search called on default (MiniLM) vectorstore, not multilingual."""
    import asyncio
    import importlib
    from langchain_core.documents import Document

    rag = importlib.import_module("services.rag")
    calls = []

    class FakeVS:
        def __init__(self, name):
            self._name = name

        def similarity_search(self, query, **kwargs):
            calls.append(self._name)
            return [Document(page_content="test chunk", metadata={"document_title": "T"})]

    class FakeLLM:
        def with_structured_output(self, schema):
            return self

        async def ainvoke(self, messages):
            from models.advisory import AdvisoryResponse, ContextMeta
            return AdvisoryResponse(
                problem_summary="test",
                likely_causes=[],
                recommended_actions=[],
                products_rates=[],
                warnings=[],
                confidence="High",
                confidence_explanation="test",
                language="en",
                citations=[],
                context_meta=ContextMeta(
                    soil_data_available=False,
                    weather_data_available=False,
                    county_fips="05001",
                ),
            )

    monkeypatch.setattr(rag, "_vectorstore", FakeVS("en"))
    monkeypatch.setattr(rag, "_vectorstore_es", FakeVS("es"))
    monkeypatch.setattr(rag, "_get_llm", lambda: FakeLLM())

    async def fake_get_context(_fips):
        return {"soil": {}, "weather": {}}

    monkeypatch.setattr(rag, "get_context", fake_get_context)

    import services.citation_guard_v2 as cgv2

    async def fake_verify(answer, chunks):
        return {"confidence_score": 0.9, "claim_verification": []}

    monkeypatch.setattr(cgv2, "verify_answer", fake_verify)

    asyncio.run(rag.run_rag_query(
        message="How do I control blast disease in rice?",
        county_fips="05001",
        language="en",
        category="IN_SCOPE_RICE",
        session_history=[],
        detected_lang="en",
    ))

    assert calls == ["en"], f"Expected EN vectorstore only, got calls={calls}"


def test_run_rag_query_es_falls_back_to_en_when_multilingual_unavailable(monkeypatch):
    """When _get_vectorstore_es() returns None, ES queries fall back to EN vectorstore."""
    import asyncio
    import importlib
    from langchain_core.documents import Document

    rag = importlib.import_module("services.rag")
    calls = []

    class FakeVS:
        def __init__(self, name):
            self._name = name

        def similarity_search(self, query, **kwargs):
            calls.append(self._name)
            return [Document(page_content="test chunk", metadata={"document_title": "T"})]

    class FakeLLM:
        def with_structured_output(self, schema):
            return self

        async def ainvoke(self, messages):
            from models.advisory import AdvisoryResponse, ContextMeta
            return AdvisoryResponse(
                problem_summary="test",
                likely_causes=[],
                recommended_actions=[],
                products_rates=[],
                warnings=[],
                confidence="High",
                confidence_explanation="test",
                language="es",
                citations=[],
                context_meta=ContextMeta(
                    soil_data_available=False,
                    weather_data_available=False,
                    county_fips="05001",
                ),
            )

    monkeypatch.setattr(rag, "_vectorstore", FakeVS("en"))
    # Simulate unavailable multilingual index by patching _get_vectorstore_es to return None
    monkeypatch.setattr(rag, "_get_vectorstore_es", lambda: None)
    monkeypatch.setattr(rag, "_get_llm", lambda: FakeLLM())

    async def fake_get_context(_fips):
        return {"soil": {}, "weather": {}}

    monkeypatch.setattr(rag, "get_context", fake_get_context)

    import services.citation_guard_v2 as cgv2

    async def fake_verify(answer, chunks):
        return {"confidence_score": 0.9, "claim_verification": []}

    monkeypatch.setattr(cgv2, "verify_answer", fake_verify)

    asyncio.run(rag.run_rag_query(
        message="¿Cómo controlo el acaro en arroz?",
        county_fips="05001",
        language="es",
        category="IN_SCOPE_RICE",
        session_history=[],
        detected_lang="es",
    ))

    assert calls == ["en"], f"Expected fallback to EN vectorstore, got calls={calls}"
