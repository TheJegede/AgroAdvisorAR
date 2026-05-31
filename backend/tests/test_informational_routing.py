import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
import importlib
from models.advisory import AdvisoryResponse, ContextMeta, Cause, Product, Citation


def test_namespaces_for_with_suffixes():
    rag = importlib.import_module("services.rag")
    # Verify exact suffix matching
    assert rag._namespaces_for("IN_SCOPE_RICE:INFO") == ["rice"]
    assert rag._namespaces_for("IN_SCOPE_RICE:DIAG") == ["rice"]
    # Verify backward compatibility (no suffix)
    assert rag._namespaces_for("IN_SCOPE_RICE") == ["rice"]
    # Verify general ag maps to all crop namespaces
    assert sorted(rag._namespaces_for("IN_SCOPE_GENERAL_AG:INFO")) == sorted(["rice", "soybeans", "poultry"])
    assert sorted(rag._namespaces_for("IN_SCOPE_GENERAL_AG")) == sorted(["rice", "soybeans", "poultry"])


def test_advisory_to_verifiable_text_includes_informational_fields():
    rag = importlib.import_module("services.rag")
    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    
    resp = AdvisoryResponse(
        response_type="informational",
        problem_summary="Summary claim.",
        detailed_explanation="This is a detailed explanation of soil test reports.",
        key_points=["Point 1: check pH.", "Point 2: check P & K."],
        likely_causes=[],
        recommended_actions=[],
        products_rates=[],
        warnings=["Safe handling warning."],
        citations=[],
        confidence="High",
        confidence_explanation="Grounded in guide.",
        language="en",
        context_meta=ctx,
    )
    
    text = rag._advisory_to_verifiable_text(resp)
    
    assert "Summary claim." in text
    assert "This is a detailed explanation of soil test reports." in text
    assert "Point 1: check pH." in text
    assert "Point 2: check P & K." in text
    # Warnings are excluded by design
    assert "Safe handling warning." not in text


@pytest.mark.anyio
async def test_postprocess_scrubs_scaffolding_from_informational_fields():
    rag = importlib.import_module("services.rag")
    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    
    resp = AdvisoryResponse(
        response_type="informational",
        problem_summary="Document 1: Summary.",
        detailed_explanation="[RETRIEVED DOCUMENT CONTEXT] Explanation here.",
        key_points=["Document 2: Point one."],
        likely_causes=[],
        recommended_actions=[],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="High",
        confidence_explanation="Good.",
        language="en",
        context_meta=ctx,
    )
    
    # Run postprocess (using disabled NLI guard to bypass network calls)
    import config
    original_guard_enabled = config.NLI_CITATION_GUARD_ENABLED
    config.NLI_CITATION_GUARD_ENABLED = False
    
    try:
        out = await rag._postprocess_async(resp, [], {}, {}, "05001")
        assert out.problem_summary == "Summary."
        assert out.detailed_explanation == "Explanation here."
        assert out.key_points == ["Point one."]
    finally:
        config.NLI_CITATION_GUARD_ENABLED = original_guard_enabled
