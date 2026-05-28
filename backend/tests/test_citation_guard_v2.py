import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.advisory import AdvisoryResponse, ClaimResult, ContextMeta


def test_advisory_response_has_optional_nli_fields():
    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    resp = AdvisoryResponse(
        problem_summary="Test",
        likely_causes=[],
        recommended_actions=[],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="High",
        confidence_explanation="Test",
        language="en",
        context_meta=ctx,
    )
    assert resp.confidence_score is None
    assert resp.claim_verification is None
    assert resp.escalation is None


def test_claim_result_labels():
    cr = ClaimResult(claim="Rice needs water.", label="ENTAILED", score=0.85)
    assert cr.label == "ENTAILED"
    assert cr.score == 0.85


def test_advisory_response_with_nli_fields():
    ctx = ContextMeta(soil_data_available=True, weather_data_available=True, county_fips="05001")
    cr = ClaimResult(claim="Apply herbicide at V3.", label="ENTAILED", score=0.9)
    resp = AdvisoryResponse(
        problem_summary="Palmer amaranth detected.",
        likely_causes=[],
        recommended_actions=["Apply herbicide"],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="Medium",
        confidence_explanation="Two sources support.",
        language="en",
        context_meta=ctx,
        confidence_score=0.78,
        claim_verification=[cr],
        escalation=None,
    )
    assert resp.confidence_score == 0.78
    assert len(resp.claim_verification) == 1
