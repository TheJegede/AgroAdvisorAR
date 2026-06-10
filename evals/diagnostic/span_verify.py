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


def fact_retrieved(gold_snippet: Optional[str], judge_span: Optional[str],
                   chunks: list[dict]) -> bool:
    """Was the gold fact actually retrieved? Anchor on the verbatim human
    gold_snippet (transcribe-don't-invent) first; fall back to the judge's
    located span for paraphrase coverage. The judge span is LLM output that
    can stitch across the chunk join or drift in whitespace, so it is the
    weaker anchor — never the only one."""
    return span_in_chunks(gold_snippet, chunks) or span_in_chunks(judge_span, chunks)
