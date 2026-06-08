"""Versioned dicamba rules-as-data loader.

Each record in dicamba_rules.json is the full ruleset valid for its
[effective_start, effective_end] window (effective_end null = open-ended).
resolve_rules() returns the record effective on a given date+jurisdiction so a
spray record always reflects the rules in force when it was produced, even after
the rules later change. Mirrors the load idiom in services/alert_engine.py.
"""
import json
from datetime import date
from pathlib import Path

_DEFAULT_PATH = str(Path(__file__).parent.parent / "data" / "dicamba_rules.json")
_cache: dict[str, list[dict]] = {}


class RulesNotFoundError(Exception):
    """No rule record's effective window contains the requested date+jurisdiction."""


def _load_records(rules_path: str | None = None) -> list[dict]:
    """Load + cache the raw dicamba_rules.json array. rules_path overrides for tests."""
    path = rules_path or _DEFAULT_PATH
    if path not in _cache:
        with open(path) as f:
            _cache[path] = json.load(f)
    return _cache[path]


def resolve_rules(
    on_date: date, jurisdiction: str = "AR", rules_path: str | None = None
) -> dict:
    """Return the rule record effective on on_date for jurisdiction.

    A record matches when effective_start <= on_date <= (effective_end or +inf).
    If several match, the one with the latest effective_start wins (most recent
    supersedes). Raise RulesNotFoundError if none match.
    """
    candidates = []
    for rec in _load_records(rules_path):
        if rec.get("jurisdiction") != jurisdiction:
            continue
        start = date.fromisoformat(rec["effective_start"])
        end_raw = rec.get("effective_end")
        end = date.fromisoformat(end_raw) if end_raw else date.max
        if start <= on_date <= end:
            candidates.append((start, rec))
    if not candidates:
        raise RulesNotFoundError(
            f"No dicamba rules effective on {on_date.isoformat()} for {jurisdiction}"
        )
    candidates.sort(key=lambda pair: pair[0])
    return candidates[-1][1]


def in_season(rules: dict, on_date: date) -> bool:
    """True if season_window.start <= on_date <= season_window.end."""
    window = rules["season_window"]
    start = date.fromisoformat(window["start"])
    end = date.fromisoformat(window["end"])
    return start <= on_date <= end


def approved_product_ids(rules: dict) -> set[str]:
    return {p["id"] for p in rules["approved_products"]}


def wind_bounds(rules: dict) -> tuple[float, float]:
    wind = rules["weather_thresholds"]["wind_mph"]
    return float(wind["min"]), float(wind["max"])


def temp_bounds(rules: dict) -> tuple[float, float]:
    temp = rules["weather_thresholds"]["air_temp_f"]
    return float(temp["min"]), float(temp["max"])


def rain_free_hours_required(rules: dict) -> int:
    return int(rules["weather_thresholds"]["rain_free_hours_required"])


def buffers_ft(rules: dict) -> dict:
    """Buffer distances in feet (research_station, organic_specialty, non_tolerant_crop)."""
    return rules["buffers_ft"]


def downwind_half_angle_deg(rules: dict) -> float:
    """Half-angle (deg) of the downwind cone used by Gate D geometry."""
    return float(rules["weather_thresholds"]["downwind_half_angle_deg"])
