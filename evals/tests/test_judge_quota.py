# evals/tests/test_judge_quota.py
"""F15 — _is_quota_error must not treat context_length_exceeded as a quota error
(that misroutes oversized prompts to the DeepInfra fallback, which also fails)."""
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parents[1]
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))

import judge


def test_context_length_exceeded_is_not_quota():
    assert judge._is_quota_error(Exception("Error: context_length_exceeded")) is False
    assert judge._is_quota_error(Exception("maximum context length is 8192 tokens")) is False


def test_real_rate_limits_are_quota():
    assert judge._is_quota_error(Exception("rate_limit_exceeded")) is True
    assert judge._is_quota_error(Exception("429 Too Many Requests")) is True
    assert judge._is_quota_error(Exception("quota exceeded for this month")) is True


def test_unrelated_error_is_not_quota():
    assert judge._is_quota_error(Exception("invalid api key")) is False
