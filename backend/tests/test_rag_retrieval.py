import sys, importlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _FakeDoc:
    def __init__(self, doc_id):
        self.id = doc_id


class _FakeVectorStore:
    """Records which namespaces were queried; returns per-namespace (doc, score)."""

    _DATA = {
        "rice": [(_FakeDoc("r1"), 0.9), (_FakeDoc("r2"), 0.4)],
        "soybeans": [(_FakeDoc("s1"), 0.7)],
        "poultry": [(_FakeDoc("p1"), 0.2)],
    }

    def __init__(self):
        self.queried_namespaces = []

    def similarity_search_with_score(self, query, k, namespace):
        self.queried_namespaces.append(namespace)
        return self._DATA.get(namespace, [])


def test_general_ag_resolves_to_all_crop_namespaces():
    rag = importlib.import_module("services.rag")
    # GENERAL_AG must fan out across the populated crop namespaces, NOT the empty
    # default namespace (the bug: it mapped to None -> Pinecone default "" -> 0 docs).
    assert rag._namespaces_for("IN_SCOPE_GENERAL_AG") == ["rice", "soybeans", "poultry"]
    # A specific crop still resolves to its single namespace.
    assert rag._namespaces_for("IN_SCOPE_RICE") == ["rice"]


def test_fanout_search_merges_namespaces_by_score():
    rag = importlib.import_module("services.rag")
    vs = _FakeVectorStore()
    docs = rag._fanout_search(vs, "cover crop after rice", 3, ["rice", "soybeans", "poultry"])
    # All crop namespaces were searched.
    assert set(vs.queried_namespaces) == {"rice", "soybeans", "poultry"}
    # Results merged and ordered by descending score, trimmed to k=3.
    assert [d.id for d in docs] == ["r1", "s1", "r2"]  # 0.9, 0.7, 0.4


# --- Title-match citation guard (fix 1A) ---------------------------------

import asyncio


class _MetaDoc:
    """Retrieval doc with arbitrary metadata + page_content (mimics langchain Document)."""

    def __init__(self, metadata, page_content=""):
        self.metadata = metadata
        self.page_content = page_content


def _make_advisory(citations_titles):
    from models.advisory import (
        AdvisoryResponse, Citation, ContextMeta,
    )
    return AdvisoryResponse(
        problem_summary="Rice sheath blight from high humidity.",
        likely_causes=[],
        recommended_actions=["Apply a labeled fungicide at first sign."],
        products_rates=[],
        warnings=[],
        citations=[Citation(document_title=t, section="1") for t in citations_titles],
        confidence="High",
        confidence_explanation="grounded",
        language="en",
        context_meta=ContextMeta(
            soil_data_available=False, weather_data_available=False, county_fips="05001",
        ),
    )


def _run_postprocess(rag, result, docs):
    return asyncio.run(rag._postprocess_async(
        result=result, docs=docs, soil={}, weather={}, county_fips="05001",
    ))


def test_titleless_index_does_not_force_low(monkeypatch):
    """gte index docs carry no document_title — title guard must NOT downgrade to
    Low. Confidence stays as the LLM set it; NLI (Step 3) governs instead."""
    rag = importlib.import_module("services.rag")
    monkeypatch.setattr(rag.config, "NLI_CITATION_GUARD_ENABLED", False)

    result = _make_advisory(["Rice Disease MP154"])
    docs = [_MetaDoc({"namespace": "rice"}), _MetaDoc({"namespace": "rice"})]

    out = _run_postprocess(rag, result, docs)

    assert out.confidence == "High"            # not forced to Low
    assert len(out.citations) == 1             # citations preserved, not stripped


def test_titled_index_still_downgrades_on_no_match(monkeypatch):
    """When titles ARE present and no citation matches a retrieved title, the
    guard still forces Low (original behavior intact)."""
    rag = importlib.import_module("services.rag")
    monkeypatch.setattr(rag.config, "NLI_CITATION_GUARD_ENABLED", False)

    result = _make_advisory(["Nonexistent Doc"])
    docs = [_MetaDoc({"document_title": "Rice Disease MP154"})]

    out = _run_postprocess(rag, result, docs)

    assert out.confidence == "Low"


def test_titled_index_keeps_only_matching_citations(monkeypatch):
    rag = importlib.import_module("services.rag")
    monkeypatch.setattr(rag.config, "NLI_CITATION_GUARD_ENABLED", False)

    result = _make_advisory(["Rice Disease MP154", "Bogus Doc"])
    docs = [_MetaDoc({"document_title": "Rice Disease MP154"})]

    out = _run_postprocess(rag, result, docs)

    assert out.confidence == "High"
    assert [c.document_title for c in out.citations] == ["Rice Disease MP154"]


# --- Task 1.1: suppressed field default -----------------------------------


def test_advisory_response_has_suppressed_default_false():
    a = _make_advisory([])
    assert a.suppressed is False


# --- Task 1.2: confidence label reconciliation + suppressed flag ----------


def _patch_guard(rag, monkeypatch, score):
    """Force the NLI guard on and stub verify_answer to a fixed score."""
    monkeypatch.setattr(rag.config, "NLI_CITATION_GUARD_ENABLED", True)

    async def _fake(answer, chunks):
        return {"confidence_score": score, "claim_verification": [], "escalation": None}

    monkeypatch.setattr(rag.citation_guard_v2, "verify_answer", _fake)


def test_suppression_forces_low_and_suppressed_flag(monkeypatch):
    rag = importlib.import_module("services.rag")
    _patch_guard(rag, monkeypatch, 0.0)
    result = _make_advisory([]).model_copy(update={"confidence": "High"})
    out = _run_postprocess(rag, result, [_MetaDoc({"namespace": "rice"}, "rice content")])
    assert out.confidence == "Low"
    assert out.suppressed is True
    assert out.problem_summary == ""
    assert out.warnings == []              # escalation NOT duplicated as a warning
    assert out.recommended_actions == []


def test_escalation_band_downgrades_high_to_medium(monkeypatch):
    rag = importlib.import_module("services.rag")
    _patch_guard(rag, monkeypatch, 0.3)    # in [SUPPRESSION=0.2, ESCALATION=0.4)
    result = _make_advisory([]).model_copy(update={"confidence": "High"})
    out = _run_postprocess(rag, result, [_MetaDoc({"namespace": "rice"}, "rice content")])
    assert out.confidence == "Medium"
    assert out.suppressed is False


def test_high_score_keeps_llm_confidence(monkeypatch):
    rag = importlib.import_module("services.rag")
    _patch_guard(rag, monkeypatch, 0.9)
    result = _make_advisory([]).model_copy(update={"confidence": "High"})
    out = _run_postprocess(rag, result, [_MetaDoc({"namespace": "rice"}, "rice content")])
    assert out.confidence == "High"
    assert out.suppressed is False


# --- Task 1.3: _strip_scaffolding removes [RETRIEVED DOCUMENT CONTEXT] ---


def test_strip_scaffolding_removes_context_header():
    rag = importlib.import_module("services.rag")
    assert rag._strip_scaffolding("Read the report, see [RETRIEVED DOCUMENT CONTEXT]") == "Read the report, see"
    assert rag._strip_scaffolding("RETRIEVED DOCUMENT CONTEXT") == ""
    assert rag._strip_scaffolding("Document 3: rice guide") == "rice guide"   # still strips Document N:
