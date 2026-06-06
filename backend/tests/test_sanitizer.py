# backend/tests/test_sanitizer.py
"""F13 — the length cap must run AFTER NFKC normalization so compatibility
characters that expand cannot slip past the cap (token amplification)."""
import importlib
import sys
from pathlib import Path
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_normalized_length_over_cap_rejected():
    san = importlib.import_module("services.sanitizer")
    # 50 raw chars that NFKC-expand to ~18 each → ~900 normalized (> 800).
    msg = "ﷺ" * 50
    assert len(msg) < san.MAX_MESSAGE_LENGTH       # passes a raw-length check
    with pytest.raises(san.MessageTooLong):
        san.sanitize(msg)


def test_normal_message_passes():
    san = importlib.import_module("services.sanitizer")
    out = san.sanitize("Why is my rice yellowing at V3?")
    assert "rice" in out


def test_plain_overlong_message_rejected():
    san = importlib.import_module("services.sanitizer")
    with pytest.raises(san.MessageTooLong):
        san.sanitize("a" * (san.MAX_MESSAGE_LENGTH + 1))
