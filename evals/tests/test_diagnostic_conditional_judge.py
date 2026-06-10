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
