"""Exact-normalized, reference-safe advisory cache. First-turn only. Stores ONLY
informational, rate-free, warning-free, non-time-sensitive advisories so a cached
answer can never be a stale/mismatched safety reply. Python port of the PWA
predicate in frontend/src/lib/offlineTiering.js."""
import hashlib
import json
import re

import config
from services.cache import cache_get, cache_set

# Parity with offlineTiering.js TIME_SENSITIVE_RE.
_TIME_SENSITIVE_RE = re.compile(
    r"\b(spray|spraying|dicamba|engenia|xtendimax|tavium|application window|apply|"
    r"rate|oz/a|pt/a|inversion|burndown|pre-?harvest|window|today|forecast|wind)\b",
    re.IGNORECASE,
)


def _normalize(q: str) -> str:
    # Lowercase, drop all punctuation (anywhere, not just edges), collapse
    # whitespace. A mid-string comma must not split an otherwise-identical query.
    lowered = re.sub(r"[^\w\s]", " ", (q or "").lower())
    return re.sub(r"\s+", " ", lowered).strip()


def _profile_sig(rice_fields) -> str:
    if not rice_fields:
        return ""
    items = sorted(
        (str(f.get("field_name", "")), str(f.get("last_flood_date", "")))
        for f in rice_fields
    )
    return hashlib.sha1(json.dumps(items).encode()).hexdigest()[:12]


def answer_cache_key(en_message: str, language: str, county_fips: str, rice_fields) -> str:
    raw = f"{_normalize(en_message)}|{language}|{county_fips}|{_profile_sig(rice_fields)}"
    return "answer:" + hashlib.sha1(raw.encode()).hexdigest()


def get_cached_answer(key: str):
    return cache_get(key)


def set_cached_answer(key: str, advisory: dict, ttl: int = config.REDIS_TTL_SECONDS) -> None:
    cache_set(key, advisory, ttl=ttl)


def _text_blob(advisory: dict) -> str:
    parts = [
        advisory.get("problem_summary") or "",
        advisory.get("detailed_explanation") or "",
        *(advisory.get("recommended_actions") or []),
        *(advisory.get("key_points") or []),
    ]
    return " ".join(parts)


def is_cacheable_as_reference(advisory: dict) -> bool:
    if not isinstance(advisory, dict):
        return False
    if advisory.get("suppressed"):
        return False
    if advisory.get("response_type") != "informational":
        return False
    if advisory.get("products_rates"):
        return False
    if advisory.get("warnings"):
        return False
    if _TIME_SENSITIVE_RE.search(_text_blob(advisory)):
        return False
    return True
