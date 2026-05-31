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


def test_score_answer_mean_entailment_prob_all_claims():
    # Mean entailment probability across ALL claims (not only ENTAILED-labeled).
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [
        ClaimResult(claim="A", label="ENTAILED", score=0.9),
        ClaimResult(claim="B", label="NEUTRAL", score=0.4),
        ClaimResult(claim="C", label="ENTAILED", score=0.7),
    ]
    score = mod.score_answer(claims)
    assert abs(score - (0.9 + 0.4 + 0.7) / 3) < 0.001  # 0.6667


def test_score_answer_empty_returns_one():
    mod = importlib.import_module("services.citation_guard_v2")
    assert mod.score_answer([]) == 1.0


def test_score_answer_partial_grounding_nonzero():
    # No hard-ENTAILED claim, no contradiction → mean entailment probability so
    # good-but-generic answers are not over-suppressed.
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [
        ClaimResult(claim="A", label="NEUTRAL", score=0.1),
        ClaimResult(claim="B", label="NEUTRAL", score=0.5),
    ]
    assert abs(mod.score_answer(claims) - 0.3) < 0.001


def test_score_answer_contradiction_forces_suppression():
    # P0.1: any CONTRADICTED claim forces 0.0 — a contradicted fact must never be
    # diluted by grounded/neutral claims and shipped.
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [
        ClaimResult(claim="A", label="ENTAILED", score=0.9),
        ClaimResult(claim="B", label="NEUTRAL", score=0.6),
        ClaimResult(claim="C", label="CONTRADICTED", score=0.05),
    ]
    # mean would be ~0.52 (would pass); contradiction override must return 0.0
    assert mod.score_answer(claims) == 0.0


def test_verify_claim_empty_chunks_ungrounded():
    # P0.2: no retrieved evidence → score 0.0 (was 0.5, which passed the gate).
    mod = importlib.import_module("services.citation_guard_v2")
    result = mod.verify_claim("Rice needs 150 lb N per acre.", [])
    assert result.score == 0.0


def test_lexical_support_credits_numbers_and_paraphrase():
    # P2.1: specific rates/terms present in the chunk score high even when not
    # verbatim-entailed; unrelated chunk scores ~0.
    mod = importlib.import_module("services.citation_guard_v2")
    chunk = "Nitrogen rates from the N-STaR program; apply 150 lb N per acre at green-up."
    assert mod._lexical_support("Apply 150 lb N per acre per N-STaR.", [chunk]) > 0.4
    assert mod._lexical_support("Apply 150 lb N per acre.", ["Soybean seeding rates for narrow rows."]) < 0.2
    # numbers and decimals are preserved as content tokens
    assert "150" in mod._content_tokens("apply 150 lb")
    assert "0.038" in mod._content_tokens("rate 0.038 lb/A")


def test_escalation_cue_found(monkeypatch):
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


def test_postprocess_stamps_confidence_score(monkeypatch):
    import asyncio
    rag = importlib.import_module("services.rag")
    guard = importlib.import_module("services.citation_guard_v2")

    async def fake_verify_answer(answer, chunks):
        return {
            "confidence_score": 0.82,
            "claim_verification": [],
            "escalation": None,
        }

    monkeypatch.setattr(guard, "verify_answer", fake_verify_answer)
    monkeypatch.setattr(guard, "escalation_cue", lambda fips: None)

    from models.advisory import AdvisoryResponse, ContextMeta
    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    resp = AdvisoryResponse(
        problem_summary="Palmer amaranth detected.",
        likely_causes=[],
        recommended_actions=["Apply herbicide at V3."],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="Medium",
        confidence_explanation="Two sources.",
        language="en",
        context_meta=ctx,
    )

    result = asyncio.run(rag._postprocess_async(resp, [], {}, {}, "05001"))
    assert result.confidence_score == 0.82


def test_verifiable_text_includes_all_advisory_fields():
    rag = importlib.import_module("services.rag")
    from models.advisory import AdvisoryResponse, Cause, ContextMeta, Product

    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    resp = AdvisoryResponse(
        problem_summary="Summary claim.",
        likely_causes=[Cause(cause="Nitrogen", explanation="Yellowing may indicate deficiency.")],
        recommended_actions=["Scout the field."],
        products_rates=[Product(product="Product A", rate="1 qt/ac", application_method="foliar")],
        warnings=["Follow label restrictions."],
        citations=[],
        confidence="Medium",
        confidence_explanation="Test.",
        language="en",
        context_meta=ctx,
    )

    text = rag._advisory_to_verifiable_text(resp)

    assert "Summary claim." in text
    assert "Nitrogen" in text
    assert "Scout the field." in text
    assert "Product A" in text
    assert "1 qt/ac" in text
    assert "Follow label restrictions." in text


def test_postprocess_skips_nli_when_disabled(monkeypatch):
    import asyncio
    rag = importlib.import_module("services.rag")
    guard = importlib.import_module("services.citation_guard_v2")

    async def fail_verify(*_args, **_kwargs):
        raise AssertionError("NLI should not run when disabled")

    monkeypatch.setattr(guard, "verify_answer", fail_verify)
    monkeypatch.setattr(rag.config, "NLI_CITATION_GUARD_ENABLED", False)

    from models.advisory import AdvisoryResponse, ContextMeta
    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    resp = AdvisoryResponse(
        problem_summary="Some advice.",
        likely_causes=[],
        recommended_actions=[],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="Low",
        confidence_explanation="Weak.",
        language="en",
        context_meta=ctx,
    )

    result = asyncio.run(rag._postprocess_async(resp, [], {}, {}, "05001"))
    assert result.confidence_score is None


def test_verify_claim_marginal_contradiction_demoted(monkeypatch):
    # Defect A: the small NLI model marks grounded paraphrases as CONTRADICTED
    # with only a marginal contradiction probability. A contradiction below the
    # confidence gate must NOT be trusted — otherwise one false positive zeroes
    # the entire answer via score_answer's hard override.
    mod = importlib.import_module("services.citation_guard_v2")
    # contradiction (0.45) is the argmax but below CONTRADICTION_MIN_PROB
    fake_scores = np.array([[0.45, 0.20, 0.35]])
    mock_model = MagicMock()
    mock_model.predict.return_value = fake_scores
    monkeypatch.setattr(mod, "_nli_model", mock_model)

    result = mod.verify_claim(
        "Sprayer calibration is often abused.",
        ["No single aspect of spray application is so abused as sprayer calibration."],
    )
    assert result.label != "CONTRADICTED"


def test_verify_claim_confident_contradiction_kept(monkeypatch):
    # Regression guard: a CONFIDENT contradiction (e.g. a wrong rate / negation)
    # must still be labeled CONTRADICTED so real errors are suppressed.
    mod = importlib.import_module("services.citation_guard_v2")
    fake_scores = np.array([[0.88, 0.05, 0.07]])
    mock_model = MagicMock()
    mock_model.predict.return_value = fake_scores
    monkeypatch.setattr(mod, "_nli_model", mock_model)

    result = mod.verify_claim("Do not irrigate.", ["Irrigation is required in dry spells."])
    assert result.label == "CONTRADICTED"


def test_strip_doc_prefix():
    rag = importlib.import_module("services.rag")
    assert rag._strip_doc_prefix("Document 4: soybeans recommended chemicals") == "soybeans recommended chemicals"
    assert rag._strip_doc_prefix("Calibrate using Document 2: rice handbook") == "Calibrate using rice handbook"
    assert rag._strip_doc_prefix("soybeans ch 13") == "soybeans ch 13"


def test_title_match_strips_document_prefix(monkeypatch):
    # Defect B: the LLM echoes the prompt's "Document N:" prefix into citation
    # titles, so exact title-matching never matched and confidence was forced
    # Low even for grounded answers. Stripping the prefix must let the match
    # succeed (confidence preserved, citation normalized).
    import asyncio
    import types
    rag = importlib.import_module("services.rag")
    monkeypatch.setattr(rag.config, "NLI_CITATION_GUARD_ENABLED", False)

    from models.advisory import AdvisoryResponse, Citation, ContextMeta
    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    resp = AdvisoryResponse(
        problem_summary="x",
        likely_causes=[],
        recommended_actions=["do"],
        products_rates=[],
        warnings=[],
        citations=[Citation(
            document_title="Document 2: soybeans ch 13 chemical application and control",
            section="s",
            url=None,
        )],
        confidence="Medium",
        confidence_explanation="ok",
        language="en",
        context_meta=ctx,
    )
    docs = [types.SimpleNamespace(
        metadata={"document_title": "soybeans ch 13 chemical application and control"},
        page_content="calibration text",
    )]
    result = asyncio.run(rag._postprocess_async(resp, docs, {}, {}, "05001"))
    assert result.confidence == "Medium"  # NOT downgraded to Low
    assert len(result.citations) == 1
    assert result.citations[0].document_title == "soybeans ch 13 chemical application and control"


def test_verifiable_text_strips_document_prefix():
    # Defect C: "Document N:" scaffolding leaking into the verifiable prose
    # produced un-entailable meta-claims ("Document 2 is related to ...") during
    # decomposition. Strip it so only real agricultural content is verified.
    rag = importlib.import_module("services.rag")
    from models.advisory import AdvisoryResponse, Cause, ContextMeta
    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    resp = AdvisoryResponse(
        problem_summary="Ensuring the right spray amount",
        likely_causes=[Cause(cause="bad calibration",
                             explanation="According to Document 4: soybeans guide, calibration is abused.")],
        recommended_actions=["Calibrate using Document 2: soybeans ch 13."],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="Low",
        confidence_explanation="x",
        language="en",
        context_meta=ctx,
    )
    text = rag._advisory_to_verifiable_text(resp)
    assert "Document 2" not in text
    assert "Document 4" not in text
    assert "soybeans ch 13" in text  # real content preserved


def test_verify_claim_high_lexical_overlap_not_contradicted(monkeypatch):
    # A claim that restates the chunk (high content-token overlap) must not be
    # honored as CONTRADICTED even if the NLI is confident — that pattern is the
    # model's systematic false positive on grounded technical claims.
    mod = importlib.import_module("services.citation_guard_v2")
    fake_scores = np.array([[0.70, 0.15, 0.15]])  # confident CONTRADICTED argmax
    mock_model = MagicMock()
    mock_model.predict.return_value = fake_scores
    monkeypatch.setattr(mod, "_nli_model", mock_model)

    # claim restates the chunk almost verbatim → lexical overlap ~1.0
    result = mod.verify_claim(
        "The formula GPM = D x D x L estimates flow rate.",
        ["GPM = D x D x L. Formula: gallons per minute estimates flow rate."],
    )
    assert result.label != "CONTRADICTED"


def test_postprocess_suppresses_body_below_threshold(monkeypatch):
    import asyncio
    rag = importlib.import_module("services.rag")
    guard = importlib.import_module("services.citation_guard_v2")

    async def fake_verify_low(answer, chunks):
        return {"confidence_score": 0.10, "claim_verification": [], "escalation": None}

    monkeypatch.setattr(guard, "verify_answer", fake_verify_low)
    monkeypatch.setattr(guard, "escalation_cue", lambda fips: "Contact: Jane Smith — 870-555-0100")

    from models.advisory import AdvisoryResponse, ContextMeta
    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    resp = AdvisoryResponse(
        problem_summary="Some advice.",
        likely_causes=[],
        recommended_actions=["Do something."],
        products_rates=[],
        warnings=[],
        citations=[],
        confidence="Low",
        confidence_explanation="Weak.",
        language="en",
        context_meta=ctx,
    )

    result = asyncio.run(rag._postprocess_async(resp, [], {}, {}, "05001"))
    assert result.problem_summary == ""
    assert result.recommended_actions == []
    assert len(result.warnings) == 1
    assert "Contact" in result.warnings[0]
