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


import importlib
import json
import os
import tempfile
import numpy as np
from unittest.mock import MagicMock, patch


def _make_county_agents_file(data: dict) -> str:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


def test_score_answer_mean_of_entailed():
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [
        ClaimResult(claim="A", label="ENTAILED", score=0.9),
        ClaimResult(claim="B", label="NEUTRAL", score=0.4),
        ClaimResult(claim="C", label="ENTAILED", score=0.7),
    ]
    score = mod.score_answer(claims)
    assert abs(score - 0.8) < 0.001


def test_score_answer_empty_returns_one():
    mod = importlib.import_module("services.citation_guard_v2")
    assert mod.score_answer([]) == 1.0


def test_score_answer_no_entailed_returns_zero():
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [
        ClaimResult(claim="A", label="CONTRADICTED", score=0.1),
        ClaimResult(claim="B", label="NEUTRAL", score=0.5),
    ]
    assert mod.score_answer(claims) == 0.0


def test_escalation_cue_found(monkeypatch, tmp_path):
    mod = importlib.import_module("services.citation_guard_v2")
    agents = {"05001": {"county": "Arkansas", "agent_name": "Jane Smith", "phone": "870-555-0100", "email": "jsmith@uada.edu"}}
    agents_file = _make_county_agents_file(agents)
    monkeypatch.setattr(mod, "_AGENTS_PATH", agents_file)
    monkeypatch.setattr(mod, "_agents_cache", None)
    try:
        result = mod.escalation_cue("05001")
        assert "Jane Smith" in result
        assert "870-555-0100" in result
    finally:
        os.unlink(agents_file)


def test_escalation_cue_missing_fips(monkeypatch):
    mod = importlib.import_module("services.citation_guard_v2")
    agents = {"05001": {"county": "Arkansas", "agent_name": "Jane Smith", "phone": "870-555-0100", "email": "jsmith@uada.edu"}}
    agents_file = _make_county_agents_file(agents)
    monkeypatch.setattr(mod, "_AGENTS_PATH", agents_file)
    monkeypatch.setattr(mod, "_agents_cache", None)
    try:
        result = mod.escalation_cue("99999")
        assert result is None
    finally:
        os.unlink(agents_file)


def test_verify_claim_entailed(monkeypatch):
    mod = importlib.import_module("services.citation_guard_v2")
    # CrossEncoder labels: index 0=contradiction, 1=entailment, 2=neutral
    fake_scores = np.array([[0.05, 0.90, 0.05], [0.10, 0.80, 0.10]])
    mock_model = MagicMock()
    mock_model.predict.return_value = fake_scores
    monkeypatch.setattr(mod, "_nli_model", mock_model)

    result = mod.verify_claim("Rice needs flooding.", ["Rice requires standing water.", "Apply fertilizer at planting."])
    assert result.label == "ENTAILED"
    assert result.score > 0.8


def test_verify_claim_contradicted(monkeypatch):
    mod = importlib.import_module("services.citation_guard_v2")
    fake_scores = np.array([[0.88, 0.05, 0.07]])
    mock_model = MagicMock()
    mock_model.predict.return_value = fake_scores
    monkeypatch.setattr(mod, "_nli_model", mock_model)

    result = mod.verify_claim("Do not irrigate.", ["Irrigation is required in dry spells."])
    assert result.label == "CONTRADICTED"
