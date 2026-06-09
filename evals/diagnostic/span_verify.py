# evals/diagnostic/span_verify.py
"""Deterministic verification that a judge-returned span is really in the chunks."""
import re
from typing import Optional


def _normalize(text: str) -> str:
    # Collapse all whitespace to single spaces, lowercase. No model involved.
    return re.sub(r"\s+", " ", text).strip().lower()


def span_in_chunks(span: Optional[str], chunks: list[dict]) -> bool:
    if not span or not span.strip():
        return False
    needle = _normalize(span)
    if not needle:
        return False
    for chunk in chunks:
        haystack = _normalize(chunk.get("snippet", ""))
        if needle in haystack:
            return True
    return False
