# evals/tests/test_diagnostic_conditional_judge.py
from evals.diagnostic.conditional_judge import flatten_advisory


def test_flatten_includes_all_answer_bearing_fields():
    advisory = {
        "problem_summary": "Rice stink bug control.",
        "detailed_explanation": "Thresholds vary by week after heading.",
        "key_points": ["5 per 10 sweeps weeks 1-2", "10 per 10 sweeps weeks 3-4"],
        "recommended_actions": ["Sweep weekly after 75% heading"],
        "products_rates": [
            {"product": "Tenchu", "rate": "9 oz/A", "application_method": "foliar"}
        ],
        "warnings": ["Consult label"],
    }
    text = flatten_advisory(advisory)
    assert "5 per 10 sweeps weeks 1-2" in text
    assert "10 per 10 sweeps weeks 3-4" in text
    assert "Tenchu" in text and "9 oz/A" in text
    assert "Sweep weekly after 75% heading" in text


def test_flatten_skips_none_and_empty():
    advisory = {
        "problem_summary": "X",
        "detailed_explanation": None,
        "key_points": [],
        "recommended_actions": [],
        "products_rates": [],
        "warnings": [],
    }
    text = flatten_advisory(advisory)
    assert text.strip() == "X"


import pytest

from evals.diagnostic.conditional_judge import (
    parse_conditional_response,
    build_conditional_prompt,
    judge_conditional,
    CompletenessResult,
    _is_transient,
)


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FlakyLLM:
    def __init__(self, error, fail_times, content='{"preserved": true, "missing": null}'):
        self.error = error
        self.fail_times = fail_times
        self.content = content
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.error
        return _FakeResp(self.content)


def test_parse_preserved_true():
    res = parse_conditional_response('{"preserved": true, "missing": null}')
    assert res.preserved is True
    assert res.missing is None


def test_parse_preserved_false_with_missing():
    res = parse_conditional_response(
        '{"preserved": false, "missing": "dropped the soil-texture branches"}'
    )
    assert res.preserved is False
    assert res.missing == "dropped the soil-texture branches"


def test_parse_strips_code_fence():
    res = parse_conditional_response('```json\n{"preserved": true, "missing": null}\n```')
    assert res.preserved is True


def test_parse_garbage_is_safe_not_preserved():
    # Unparseable judge output must never count as a pass.
    res = parse_conditional_response("the model rambled")
    assert res.preserved is False


def test_prompt_carries_gold_and_candidate():
    prompt = build_conditional_prompt(
        gold_answer="0.8 pt/A coarse, 1.6 pt/A medium, 2.4 pt/A fine soil",
        candidate_answer="Apply 1.6 pt/A.",
    )
    assert "0.8 pt/A coarse" in prompt
    assert "Apply 1.6 pt/A." in prompt
    assert "preserved" in prompt


def test_judge_retries_transient_then_succeeds():
    llm = _FlakyLLM(RuntimeError("503 UNAVAILABLE"), fail_times=2)
    res = judge_conditional("gold", "candidate", llm=llm, sleep=lambda _s: None)
    assert res.preserved is True
    assert llm.calls == 3


def test_judge_reraises_after_max_attempts():
    llm = _FlakyLLM(RuntimeError("503 UNAVAILABLE"), fail_times=99)
    with pytest.raises(RuntimeError):
        judge_conditional("g", "c", llm=llm, max_attempts=3, sleep=lambda _s: None)
    assert llm.calls == 3
