import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import tempfile
import os
from datetime import date, timedelta


def _write_thresholds():
    data = {
        "poorly drained":          {"dry_rate_cm_per_day": 0.5, "threshold_cm": 15},
        "somewhat poorly drained": {"dry_rate_cm_per_day": 0.8, "threshold_cm": 15},
        "moderately well drained": {"dry_rate_cm_per_day": 1.2, "threshold_cm": 15},
        "well drained":            {"dry_rate_cm_per_day": 1.5, "threshold_cm": 15},
        "default":                 {"dry_rate_cm_per_day": 0.8, "threshold_cm": 15},
    }
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, tmp)
    tmp.close()
    return tmp.name


def _make_scheduler(path):
    import importlib
    import services.awd_scheduler as mod
    mod._thresholds = None  # reset cache
    mod._THRESHOLDS_PATH = Path(path)
    return mod


def test_re_flood_now_when_past_threshold():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        last_flood = date.today() - timedelta(days=30)
        # 30 * 0.8 = 24cm > 15cm threshold
        r = mod.compute_awd_stage("f1", last_flood, "somewhat poorly drained", None)
        assert r.days_to_threshold == 0
        assert r.recommendation == "re-flood now"
    finally:
        os.unlink(path)


def test_prepare_to_reflood_within_2_days():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        # At 0.8 cm/day, threshold at 15cm = 18.75 days
        # 17 days elapsed: 13.6 cm depth, 1.4 cm left = ceil(1.4/0.8) = 2 days
        last_flood = date.today() - timedelta(days=17)
        r = mod.compute_awd_stage("f1", last_flood, "somewhat poorly drained", None)
        assert r.days_to_threshold <= 2
        assert r.recommendation == "prepare to re-flood"
    finally:
        os.unlink(path)


def test_maintain_flood_early_in_cycle():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        last_flood = date.today() - timedelta(days=3)
        r = mod.compute_awd_stage("f1", last_flood, "somewhat poorly drained", None)
        assert r.days_to_threshold > 2
        assert r.recommendation == "maintain flood"
    finally:
        os.unlink(path)


def test_well_drained_faster_dry_rate():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        # 9 days * 1.5 cm/day = 13.5 cm depth; ceil((15-13.5)/1.5) = 1 day → prepare
        last_flood = date.today() - timedelta(days=9)
        r = mod.compute_awd_stage("f1", last_flood, "well drained", None)
        assert r.recommendation in ("prepare to re-flood", "re-flood now")
    finally:
        os.unlink(path)


def test_unknown_drainage_class_uses_default():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        last_flood = date.today() - timedelta(days=1)
        r = mod.compute_awd_stage("f1", last_flood, "bogus drainage class", None)
        assert r.recommendation == "maintain flood"
    finally:
        os.unlink(path)


def test_aquifer_stress_passes_through():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        last_flood = date.today()
        r = mod.compute_awd_stage("North 40", last_flood, "default", 5.2, "critical")
        assert r.aquifer_stress_level == "critical"
        assert r.well_depth_m == 5.2
        assert r.field_name == "North 40"
    finally:
        os.unlink(path)


def test_format_awd_context_contains_field_and_recommendation():
    path = _write_thresholds()
    try:
        mod = _make_scheduler(path)
        last_flood = date.today() - timedelta(days=30)
        r = mod.compute_awd_stage("North 40", last_flood, "somewhat poorly drained", None)
        ctx = mod.format_awd_context([r])
        assert "North 40" in ctx
        assert "re-flood now" in ctx
        assert "[AWD IRRIGATION STATUS]" in ctx
    finally:
        os.unlink(path)
