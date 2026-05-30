import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.advisory import AdvisoryDraft, AdvisoryResponse, ContextMeta


# Guard-computed fields must NOT be on the LLM-facing schema — exposing them to
# with_structured_output let the model hallucinate claim verifications and crash
# generation on enum-label typos ("ENTAILLED") / wrong types.
GUARD_FIELDS = {"confidence_score", "claim_verification", "escalation"}


def test_llm_draft_excludes_guard_fields():
    assert GUARD_FIELDS.isdisjoint(AdvisoryDraft.model_fields), (
        "AdvisoryDraft (LLM-facing) must not expose guard-computed fields"
    )


def test_full_response_includes_guard_fields():
    assert GUARD_FIELDS.issubset(AdvisoryResponse.model_fields)


def test_draft_carries_all_llm_authored_fields():
    expected = {
        "problem_summary", "likely_causes", "recommended_actions",
        "products_rates", "warnings", "citations", "confidence",
        "confidence_explanation", "language", "context_meta",
    }
    assert expected.issubset(AdvisoryDraft.model_fields)


def test_response_is_constructable_from_draft_dump():
    draft = AdvisoryDraft(
        problem_summary="Rice sheath blight.",
        likely_causes=[],
        recommended_actions=["Apply fungicide."],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="High",
        confidence_explanation="grounded",
        language="en",
        context_meta=ContextMeta(
            soil_data_available=False, weather_data_available=False, county_fips="05031",
        ),
    )
    full = AdvisoryResponse(**draft.model_dump())
    assert full.problem_summary == "Rice sheath blight."
    # Guard fields default to None until the post-hoc guard fills them.
    assert full.confidence_score is None
    assert full.claim_verification is None
    assert full.escalation is None
