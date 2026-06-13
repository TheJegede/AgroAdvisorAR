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
