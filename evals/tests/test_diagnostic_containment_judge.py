# evals/tests/test_diagnostic_containment_judge.py
from evals.diagnostic.containment_judge import parse_judge_response, build_judge_prompt


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
