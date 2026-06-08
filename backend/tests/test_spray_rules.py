import json
import sys
from datetime import date
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import spray_rules  # noqa: E402


def _thresholds():
    return {
        "wind_mph": {"min": 3.0, "max": 10.0},
        "boom_height_ft_max": 2.0,
        "droplet_size": "Ultra Coarse or coarser (per label)",
        "time_of_day": {"earliest": "sunrise", "latest": "sunset", "note": "n/a"},
        "rain_free_hours_required": 48,
        "air_temp_f": {"min": 50.0, "max": 91.0},
    }


def _buffers():
    return {"research_station": 5280, "organic_specialty": 2640, "non_tolerant_crop": 1320}


# Fixture records:
#   A: AR 2025 (closed window)
#   B: AR 2026-01-01 → open
#   C: AR 2026-05-01 → open  (overlaps B; later effective_start should supersede)
#   D: MO 2026-01-01 → open  (different jurisdiction)
_RECORDS = [
    {
        "rule_version": "2025-AR",
        "jurisdiction": "AR",
        "effective_start": "2025-01-01",
        "effective_end": "2025-12-31",
        "season_window": {"start": "2025-04-15", "end": "2025-06-30"},
        "buffers_ft": _buffers(),
        "approved_products": [{"id": "engenia"}, {"id": "xtendimax"}],
        "required_additives": [],
        "prohibited_additives": [],
        "weather_thresholds": _thresholds(),
    },
    {
        "rule_version": "2026-AR-OTT",
        "jurisdiction": "AR",
        "effective_start": "2026-01-01",
        "effective_end": None,
        "season_window": {"start": "2026-04-15", "end": "2026-06-30"},
        "buffers_ft": _buffers(),
        "approved_products": [{"id": "engenia"}, {"id": "xtendimax"}, {"id": "tavium"}],
        "required_additives": [],
        "prohibited_additives": [],
        "weather_thresholds": _thresholds(),
    },
    {
        "rule_version": "2026-AR-REVISED",
        "jurisdiction": "AR",
        "effective_start": "2026-05-01",
        "effective_end": None,
        "season_window": {"start": "2026-04-15", "end": "2026-06-30"},
        "buffers_ft": _buffers(),
        "approved_products": [{"id": "engenia"}, {"id": "xtendimax"}, {"id": "tavium"}],
        "required_additives": [],
        "prohibited_additives": [],
        "weather_thresholds": _thresholds(),
    },
    {
        "rule_version": "2026-MO",
        "jurisdiction": "MO",
        "effective_start": "2026-01-01",
        "effective_end": None,
        "season_window": {"start": "2026-04-15", "end": "2026-07-15"},
        "buffers_ft": _buffers(),
        "approved_products": [{"id": "engenia"}],
        "required_additives": [],
        "prohibited_additives": [],
        "weather_thresholds": _thresholds(),
    },
]


@pytest.fixture()
def rules_path(tmp_path):
    p = tmp_path / "dicamba_rules.json"
    p.write_text(json.dumps(_RECORDS))
    return str(p)


@pytest.fixture()
def ar_2026(rules_path):
    """The record effective for a mid-2026 AR date (the revised one)."""
    return spray_rules.resolve_rules(date(2026, 6, 8), "AR", rules_path=rules_path)


def test_resolve_rules_returns_record_in_window(rules_path):
    rules = spray_rules.resolve_rules(date(2025, 6, 1), "AR", rules_path=rules_path)
    assert rules["rule_version"] == "2025-AR"


def test_resolve_rules_picks_latest_effective_start_when_overlapping(rules_path):
    rules = spray_rules.resolve_rules(date(2026, 6, 8), "AR", rules_path=rules_path)
    assert rules["rule_version"] == "2026-AR-REVISED"


def test_resolve_rules_open_ended_effective_end_null(rules_path):
    rules = spray_rules.resolve_rules(date(2030, 1, 1), "AR", rules_path=rules_path)
    assert rules["rule_version"] == "2026-AR-REVISED"


def test_resolve_rules_raises_when_no_window_contains_date(rules_path):
    with pytest.raises(spray_rules.RulesNotFoundError):
        spray_rules.resolve_rules(date(2020, 1, 1), "AR", rules_path=rules_path)


def test_resolve_rules_respects_jurisdiction(rules_path):
    rules = spray_rules.resolve_rules(date(2026, 6, 8), "MO", rules_path=rules_path)
    assert rules["rule_version"] == "2026-MO"


def test_in_season_true_within_window(ar_2026):
    assert spray_rules.in_season(ar_2026, date(2026, 5, 1)) is True


def test_in_season_false_before_start(ar_2026):
    assert spray_rules.in_season(ar_2026, date(2026, 4, 1)) is False


def test_in_season_false_after_end(ar_2026):
    assert spray_rules.in_season(ar_2026, date(2026, 7, 1)) is False


def test_buffer_and_threshold_accessors_return_expected_values(ar_2026):
    assert spray_rules.approved_product_ids(ar_2026) == {"engenia", "xtendimax", "tavium"}
    assert spray_rules.wind_bounds(ar_2026) == (3.0, 10.0)
    assert spray_rules.temp_bounds(ar_2026) == (50.0, 91.0)
    assert spray_rules.rain_free_hours_required(ar_2026) == 48


def test_shipped_data_file_loads_and_resolves_for_in_season_2026():
    """Guard: the real backend/data/dicamba_rules.json is valid + resolvable."""
    rules = spray_rules.resolve_rules(date(2026, 6, 1), "AR")
    assert rules["rule_version"]
    assert spray_rules.in_season(rules, date(2026, 6, 1)) is True
    assert spray_rules.approved_product_ids(rules)
    lo, hi = spray_rules.wind_bounds(rules)
    assert lo < hi
