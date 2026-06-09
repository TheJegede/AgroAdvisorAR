# evals/tests/test_diagnostic_pipeline_flags.py
from evals.diagnostic.pipeline_flags import is_abstention


def test_suppressed_is_abstention():
    assert is_abstention({"suppressed": True, "escalation": None}) is True


def test_escalation_present_is_abstention():
    assert is_abstention({"suppressed": False, "escalation": "Call your county agent"}) is True


def test_plain_answer_is_not_abstention():
    assert is_abstention({"suppressed": False, "escalation": None}) is False


def test_missing_keys_default_not_abstention():
    assert is_abstention({}) is False
