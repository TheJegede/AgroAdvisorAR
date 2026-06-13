import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from answerkey_judge import build_judge_prompt, _parse_judge_score


def test_build_judge_prompt_includes_both_answers():
    p = build_judge_prompt(
        query="how much nitrogen for rice",
        answer="Use about 90 lb of nitrogen per acre, split into two.",
        reference_answer="Apply 90 lb N/acre, split application.",
    )
    assert "90 lb of nitrogen" in p           # candidate answer
    assert "Apply 90 lb N/acre" in p          # reference answer
    assert "how much nitrogen for rice" in p  # query
    # must instruct source-independent grading
    assert "regardless" in p.lower() or "any correct" in p.lower()


def test_parse_judge_score_reads_verdict_line():
    assert _parse_judge_score("Reasoning: matches.\nSCORE: 1.0") == 1.0
    assert _parse_judge_score("partial\nSCORE: 0.5") == 0.5
    assert _parse_judge_score("SCORE: 0") == 0.0
    # robust to stray text / missing -> None
    assert _parse_judge_score("no verdict here") is None


from answerkey_judge import grade_with_answer_key


def test_grade_with_answer_key_skips_unkeyed_and_scores_keyed():
    keys = {"q1": {"reference_answer": "Apply 90 lb N/acre.", "validated": True}}
    calls = []
    def fake_judge(query, answer, ref):
        calls.append(query)
        return (1.0, "ok")
    # q1 keyed+validated -> judged; q2 has no key -> None (skipped)
    assert grade_with_answer_key("q1", "use ~90 lb N", keys, judge=fake_judge) == 1.0
    assert grade_with_answer_key("q2", "whatever", keys, judge=fake_judge) is None
    # unvalidated key is not used (circularity guard)
    keys2 = {"q3": {"reference_answer": "x", "validated": False}}
    assert grade_with_answer_key("q3", "x", keys2, judge=fake_judge) is None
    assert calls == ["q1"]
