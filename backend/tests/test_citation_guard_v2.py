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


def test_score_answer_drops_single_contradiction_keeps_rest():
    # One contradicted claim among grounded ones should NOT zero the whole answer;
    # the contradicted claim is dropped and the rest scored.
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [
        ClaimResult(claim="A grounded.", label="ENTAILED", score=0.9),
        ClaimResult(claim="B grounded.", label="ENTAILED", score=0.8),
        ClaimResult(claim="C off-topic.", label="CONTRADICTED", score=0.0),
    ]
    score = mod.score_answer(claims)
    assert score > 0.2  # not suppressed; ~mean(0.9, 0.8)


def test_score_answer_all_contradicted_suppresses():
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [ClaimResult(claim="x", label="CONTRADICTED", score=0.0),
              ClaimResult(claim="y", label="CONTRADICTED", score=0.0)]
    assert mod.score_answer(claims) == 0.0


def test_score_answer_safety_critical_contradiction_suppresses():
    # A contradiction on a rate/unit (e.g. wrong lb/ac) must fully suppress even
    # among grounded claims — a wrong chemical rate can harm a crop.
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [
        ClaimResult(claim="Scout the field weekly.", label="ENTAILED", score=0.9),
        ClaimResult(claim="Apply 999 lb N/ac.", label="CONTRADICTED", score=0.0),
    ]
    assert mod.score_answer(claims) == 0.0


def test_score_answer_growth_stage_contradiction_does_not_suppress():
    # A contradiction on a growth stage (e.g. V3 or R5) should NOT be treated as
    # safety-critical and therefore should not fully suppress the answer.
    mod = importlib.import_module("services.citation_guard_v2")
    from models.advisory import ClaimResult
    claims = [
        ClaimResult(claim="Scout the field weekly.", label="ENTAILED", score=0.9),
        ClaimResult(claim="Apply at V3 stage.", label="CONTRADICTED", score=0.0),
        ClaimResult(claim="Avoid application after R5.", label="CONTRADICTED", score=0.0),
    ]
    # The contradicted claims are dropped, and the rest is scored.
    score = mod.score_answer(claims)
    assert score == 0.9  # not suppressed (would be 0.0 if safety-critical)


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

    async def fake_verify_answer(answer, chunks, *args, **kwargs):
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
    assert "Follow label restrictions." not in text


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

    async def fake_verify_low(answer, chunks, *args, **kwargs):
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
    # New design: escalation is carried by result.escalation (rendered via SuppressedNotice),
    # NOT duplicated into warnings. warnings is empty to avoid showing it twice.
    assert result.warnings == []
    assert result.suppressed is True
    assert result.escalation is not None
    assert "Contact" in result.escalation


def test_judge_claims_llm_parses_labels_and_scores(monkeypatch):
    mod = importlib.import_module("services.citation_guard_v2")

    class FakeResp:
        content = (
            '[{"claim":"GPM = D x D x L estimates flow.","label":"ENTAILED","score":0.9},'
            '{"claim":"Apply 999 lb N/ac.","label":"CONTRADICTED","score":0.0}]'
        )

    class FakeLLM:
        async def ainvoke(self, messages, *args, **kwargs):
            return FakeResp()

    monkeypatch.setattr(mod, "_providers", lambda: [FakeLLM()])
    import asyncio
    results = asyncio.run(mod.judge_claims_llm(
        ["GPM = D x D x L estimates flow.", "Apply 999 lb N/ac."],
        ["GPM = D x D x L. Apply 150 lb N/ac at green-up."],
    ))
    assert results[0].label == "ENTAILED" and results[0].score >= 0.8
    assert results[1].label == "CONTRADICTED"


def test_verify_answer_uses_llm_judge_when_configured(monkeypatch):
    mod = importlib.import_module("services.citation_guard_v2")
    import asyncio

    async def fake_decompose(answer, *args, **kwargs):
        return ["claim one"]

    async def fake_judge(claims, chunks, *args, **kwargs):
        from models.advisory import ClaimResult
        return [ClaimResult(claim="claim one", label="ENTAILED", score=0.88)]

    monkeypatch.setattr(mod, "decompose_claims", fake_decompose)
    monkeypatch.setattr(mod, "judge_claims_llm", fake_judge)
    monkeypatch.setattr(mod.config, "GROUNDEDNESS_JUDGE", "llm")

    out = asyncio.run(mod.verify_answer("some answer", [{"snippet": "evidence"}]))
    assert out["confidence_score"] == 0.88
    assert out["claim_verification"][0].label == "ENTAILED"


def test_guard_thresholds_env_overridable(monkeypatch):
    """Config exposes env-overridable thresholds; guard module constants derive from config."""
    monkeypatch.setenv("GUARD_SUPPRESSION_THRESHOLD", "0.15")
    monkeypatch.setenv("GUARD_ESCALATION_THRESHOLD", "0.45")

    import config as _config
    importlib.reload(_config)
    assert _config.GUARD_SUPPRESSION_THRESHOLD == 0.15
    assert _config.GUARD_ESCALATION_THRESHOLD == 0.45

    guard = importlib.reload(importlib.import_module("services.citation_guard_v2"))
    assert guard.SUPPRESSION_THRESHOLD == 0.15
    assert guard.ESCALATION_THRESHOLD == 0.45

    # Restore defaults so other tests are unaffected.
    monkeypatch.delenv("GUARD_SUPPRESSION_THRESHOLD")
    monkeypatch.delenv("GUARD_ESCALATION_THRESHOLD")
    importlib.reload(_config)
    importlib.reload(importlib.import_module("services.citation_guard_v2"))


def test_postprocess_scrubs_document_prefix_from_displayed_fields(monkeypatch):
    # Phase 5: even with titleless retrieval (titles_present False, so the
    # title-match branch never runs), the LLM can echo "Document N:" into the
    # user-facing fields. _postprocess_async must scrub it from citation titles,
    # likely-cause cause/explanation, recommended_actions, and problem_summary
    # ALWAYS — independent of titles_present and before/regardless of the NLI step.
    import asyncio
    import types
    rag = importlib.import_module("services.rag")
    monkeypatch.setattr(rag.config, "NLI_CITATION_GUARD_ENABLED", False)

    from models.advisory import AdvisoryResponse, Cause, Citation, ContextMeta
    ctx = ContextMeta(soil_data_available=False, weather_data_available=False, county_fips="05001")
    resp = AdvisoryResponse(
        problem_summary="Document 5: nitrogen stress observed.",
        likely_causes=[Cause(cause="Document 6: deficiency",
                             explanation="Document 2: Nitrogen deficiency.")],
        recommended_actions=["Document 3: Scout weekly."],
        products_rates=[],
        warnings=[],
        citations=[Citation(document_title="Document 1: Rice Guide", section="s", url=None)],
        confidence="Medium",
        confidence_explanation="ok",
        language="en",
        context_meta=ctx,
    )
    # docs carry NO document_title → titles_present is False → prove scrub still runs.
    docs = [types.SimpleNamespace(metadata={}, page_content="some content")]

    result = asyncio.run(rag._postprocess_async(resp, docs, {}, {}, "05001"))

    assert "Document" not in result.problem_summary
    assert all("Document" not in a for a in result.recommended_actions)
    assert all("Document" not in c.cause and "Document" not in c.explanation
               for c in result.likely_causes)
    assert all("Document" not in c.document_title for c in result.citations)
    # Real content preserved.
    assert "Scout weekly." in result.recommended_actions[0]
    assert result.citations[0].document_title == "Rice Guide"
