# evals/diagnostic/conditional_judge.py
"""Conditional-completeness judge: did the GENERATED answer preserve the
condition->branch structure of the gold conditional answer?

Separate from containment_judge: containment reads the retrieved CHUNKS, this
reads the generated ANSWER. Uses Gemini 2.5-flash — a different model from the
70B generator, so the generator never grades itself.
"""
import os
import re
import json
import time
from dataclasses import dataclass
from typing import Optional


def flatten_advisory(advisory: dict) -> str:
    """Join every answer-bearing field of an advisory into one candidate string."""
    parts: list[str] = []
    for key in ("problem_summary", "detailed_explanation"):
        val = advisory.get(key)
        if val:
            parts.append(str(val))
    for key in ("key_points", "recommended_actions", "warnings"):
        for item in advisory.get(key) or []:
            if item:
                parts.append(str(item))
    for pr in advisory.get("products_rates") or []:
        bits = [pr.get("product"), pr.get("rate"), pr.get("application_method")]
        line = " ".join(b for b in bits if b)
        if line:
            parts.append(line)
    return "\n".join(parts)
