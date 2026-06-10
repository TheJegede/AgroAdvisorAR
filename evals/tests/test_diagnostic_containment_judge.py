# evals/tests/test_diagnostic_containment_judge.py
import pytest

from evals.diagnostic.containment_judge import (
    parse_judge_response,
    build_judge_prompt,
    judge_containment,
    _is_transient,
)


class _FakeResp:
    def __init__(self, content):
        self.content = content


class _FlakyLLM:
    """Fails `fail_times` with the given error, then returns a valid response."""

    def __init__(self, error, fail_times, content='{"quoted_span": "x", "partial": false}'):
        self.error = error
        self.fail_times = fail_times
        self.content = content
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.error
        return _FakeResp(self.content)


def test_parse_clean_json():
    res = parse_judge_response('{"quoted_span": "2.0 to 4.0 pt/A", "partial": false}')
    assert res.span == "2.0 to 4.0 pt/A"
    assert res.partial is False


def test_parse_null_span():
    res = parse_judge_response('{"quoted_span": null, "partial": false}')
    assert res.span is None


def test_parse_strips_code_fence():
    res = parse_judge_response('```json\n{"quoted_span": "x", "partial": true}\n```')
    assert res.span == "x"
    assert res.partial is True


def test_parse_garbage_is_safe_null():
    res = parse_judge_response("the model rambled with no json")
    assert res.span is None
    assert res.partial is False


def test_prompt_contains_gold_and_chunks_but_not_answer_request():
    prompt = build_judge_prompt(
        gold_answer="Gramoxone SL 2.0 at 2.0-4.0 pt/A",
        chunks=[{"snippet": "Apply Gramoxone SL 2.0 at 2.0 to 4.0 pt/A."}],
    )
    assert "2.0 to 4.0 pt/A" in prompt
    assert "Gramoxone SL 2.0 at 2.0-4.0" in prompt
    # The judge must never be asked to produce the answer.
    assert "quoted_span" in prompt


def test_is_transient_detects_503_and_429():
    assert _is_transient(RuntimeError("503 UNAVAILABLE high demand"))
    assert _is_transient(RuntimeError("429 rate limit"))
    assert _is_transient(RuntimeError("temporarily UNAVAILABLE"))
    assert not _is_transient(RuntimeError("400 invalid argument"))


def test_judge_retries_transient_then_succeeds():
    # A 503 spike must not crash the whole gate run — retry and recover.
    llm = _FlakyLLM(RuntimeError("503 UNAVAILABLE"), fail_times=2)
    res = judge_containment("gold", [{"snippet": "x"}], llm=llm, sleep=lambda _s: None)
    assert res.span == "x"
    assert llm.calls == 3


def test_judge_reraises_after_max_attempts():
    llm = _FlakyLLM(RuntimeError("503 UNAVAILABLE"), fail_times=99)
    with pytest.raises(RuntimeError):
        judge_containment("gold", [{"snippet": "x"}], llm=llm,
                          max_attempts=3, sleep=lambda _s: None)
    assert llm.calls == 3


def test_judge_does_not_retry_non_transient():
    llm = _FlakyLLM(RuntimeError("400 invalid argument"), fail_times=99)
    with pytest.raises(RuntimeError):
        judge_containment("gold", [{"snippet": "x"}], llm=llm,
                          max_attempts=3, sleep=lambda _s: None)
    assert llm.calls == 1
