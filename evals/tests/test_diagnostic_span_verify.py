# evals/tests/test_diagnostic_span_verify.py
from evals.diagnostic.span_verify import span_in_chunks

CHUNKS = [
    {"snippet": "Apply Gramoxone SL 2.0 at 2.0 to 4.0 pt/A for preplant burndown."},
    {"snippet": "Inversions trap spray droplets near the ground."},
]


def test_exact_span_matches():
    assert span_in_chunks("2.0 to 4.0 pt/A", CHUNKS) is True


def test_whitespace_and_case_normalized():
    assert span_in_chunks("2.0   TO 4.0   PT/A", CHUNKS) is True


def test_absent_span_does_not_match():
    assert span_in_chunks("1.5 pt/A", CHUNKS) is False


def test_none_span_is_false():
    assert span_in_chunks(None, CHUNKS) is False


def test_empty_span_is_false():
    assert span_in_chunks("   ", CHUNKS) is False
