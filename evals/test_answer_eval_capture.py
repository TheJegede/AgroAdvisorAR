import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from answer_eval_full import _capture_fields


def test_capture_fields_extracts_answer_and_full_contexts():
    adv = {
        "problem_summary": "Rice sheath blight risk is high.",
        "recommended_actions": ["Scout fields", "Apply fungicide if threshold met"],
    }
    chunks = [
        {"document_title": "MP154", "snippet": "Apply azoxystrobin at 0.2 lb ai/acre."},
        {"document_title": "FSA2042", "snippet": "Sheath blight thrives in dense canopies."},
    ]
    out = _capture_fields(adv, chunks)

    # answer is the flattened advisory prose (non-empty string)
    assert isinstance(out["answer"], str) and out["answer"].strip()
    # contexts is the list of retrieved chunk snippets, untruncated, in order
    assert out["contexts"] == [
        "Apply azoxystrobin at 0.2 lb ai/acre.",
        "Sheath blight thrives in dense canopies.",
    ]


def test_capture_fields_handles_empty_chunks():
    out = _capture_fields({"problem_summary": "x"}, [])
    assert out["contexts"] == []
    assert isinstance(out["answer"], str)


from answer_eval_full import compute_correctness


def _gold_fn_factory(score, calls):
    def fn():
        calls.append(1)
        return (score, "gold rationale")
    return fn


def test_compute_correctness_gold_mode_uses_gold_only():
    calls = []
    corr, gold, ak, rat = compute_correctness(
        "gold", "q1", "ans", {"q1": {"reference_answer": "r", "validated": True}},
        _gold_fn_factory(0.0, calls), judge=lambda q, a, r: (1.0, "ak"))
    assert (corr, gold, ak) == (0.0, 0.0, None)  # answerkey ignored in gold mode
    assert len(calls) == 1


def test_compute_correctness_answerkey_uses_key_skips_gold():
    calls = []
    corr, gold, ak, rat = compute_correctness(
        "answerkey", "q1", "ans", {"q1": {"reference_answer": "r", "validated": True}},
        _gold_fn_factory(0.0, calls), judge=lambda q, a, r: (1.0, "ak"))
    assert corr == 1.0 and ak == 1.0 and gold is None  # gold not called
    assert calls == []


def test_compute_correctness_answerkey_falls_back_to_gold_when_unkeyed():
    calls = []
    corr, gold, ak, rat = compute_correctness(
        "answerkey", "qX", "ans", {}, _gold_fn_factory(0.5, calls),
        judge=lambda q, a, r: (1.0, "ak"))
    assert corr == 0.5 and gold == 0.5 and ak is None
    assert len(calls) == 1


def test_compute_correctness_both_records_both_rulers():
    calls = []
    corr, gold, ak, rat = compute_correctness(
        "both", "q1", "ans", {"q1": {"reference_answer": "r", "validated": True}},
        _gold_fn_factory(0.0, calls), judge=lambda q, a, r: (1.0, "ak"))
    # both rulers populated; primary correctness = answerkey when keyed
    assert gold == 0.0 and ak == 1.0 and corr == 1.0
    assert len(calls) == 1  # gold still computed in both mode
