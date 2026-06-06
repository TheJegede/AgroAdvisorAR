import importlib
import sys
import json
import asyncio
import tempfile
import os
from datetime import date, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

RULES = [
    {
        "crop": "rice", "pest": "rice_water_weevil",
        "gdd_lower": 150, "gdd_upper": None, "requires_recent_flood_days": 14,
        "message_en": "RWW alert EN", "message_es": "RWW alert ES"
    },
    {
        "crop": "soybeans", "pest": "palmer_amaranth",
        "gdd_lower": 200, "gdd_upper": 450,
        "message_en": "Palmer EN", "message_es": "Palmer ES"
    },
]


def _write_rules(rules=RULES):
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(rules, tmp)
    tmp.close()
    return tmp.name


def _fake_supabase():
    inserted = []

    class FakeResult:
        data = [{"id": "alert-uuid"}]

    class FakeTable:
        def insert(self, row):
            inserted.append(row)
            return self
        def execute(self):
            return FakeResult()

    class FakeClient:
        def table(self, _):
            return FakeTable()

    return FakeClient(), inserted


def _fake_redis(key_exists=False):
    store = {}

    class FakeRedis:
        def exists(self, key):
            return 1 if key_exists else 0
        def set(self, key, val, ex=None):
            store[key] = val

    return FakeRedis(), store


async def _fake_gdd_200(fips): return 200.0
async def _fake_gdd_100(fips): return 100.0
async def _fake_gdd_500(fips): return 500.0


def _rice_fields(days_since_flood: int) -> list[dict]:
    return [{
        "field_name": "North 40",
        "last_flood_date": (date.today() - timedelta(days=days_since_flood)).isoformat(),
    }]


def test_alert_fires_when_gdd_in_range(monkeypatch):
    mod = importlib.import_module("services.alert_engine")
    supabase, inserted = _fake_supabase()
    redis, store = _fake_redis(key_exists=False)
    monkeypatch.setattr(mod, "_get_service_client", lambda: supabase)
    monkeypatch.setattr(mod, "_get_redis", lambda: redis)
    monkeypatch.setattr(mod, "compute_gdd_since_jan1", _fake_gdd_200)

    rules_path = _write_rules()
    try:
        engine = mod.AlertEngine(rules_path=rules_path)
        fired = asyncio.run(engine.run_for_farmer(
            farmer_id="farmer-1",
            county_fips="05001",
            primary_crops=["rice"],
            language="en",
            rice_fields=_rice_fields(7),
        ))
    finally:
        os.unlink(rules_path)

    assert "rice_water_weevil" in fired
    assert len(inserted) == 1
    assert inserted[0]["pest"] == "rice_water_weevil"
    assert "alert:farmer-1:rice_water_weevil" in store


def test_alert_deduped_when_redis_key_exists(monkeypatch):
    mod = importlib.import_module("services.alert_engine")
    supabase, inserted = _fake_supabase()
    redis, store = _fake_redis(key_exists=True)
    monkeypatch.setattr(mod, "_get_service_client", lambda: supabase)
    monkeypatch.setattr(mod, "_get_redis", lambda: redis)
    monkeypatch.setattr(mod, "compute_gdd_since_jan1", _fake_gdd_200)

    rules_path = _write_rules()
    try:
        engine = mod.AlertEngine(rules_path=rules_path)
        fired = asyncio.run(engine.run_for_farmer(
            farmer_id="farmer-1",
            county_fips="05001",
            primary_crops=["rice"],
            language="en",
            rice_fields=_rice_fields(7),
        ))
    finally:
        os.unlink(rules_path)

    assert fired == []
    assert inserted == []


def test_alert_skipped_when_gdd_below_lower(monkeypatch):
    mod = importlib.import_module("services.alert_engine")
    supabase, inserted = _fake_supabase()
    redis, _ = _fake_redis()
    monkeypatch.setattr(mod, "_get_service_client", lambda: supabase)
    monkeypatch.setattr(mod, "_get_redis", lambda: redis)
    monkeypatch.setattr(mod, "compute_gdd_since_jan1", _fake_gdd_100)

    rules_path = _write_rules()
    try:
        engine = mod.AlertEngine(rules_path=rules_path)
        fired = asyncio.run(engine.run_for_farmer(
            farmer_id="farmer-1",
            county_fips="05001",
            primary_crops=["rice"],
            language="en",
            rice_fields=_rice_fields(7),
        ))
    finally:
        os.unlink(rules_path)

    assert fired == []
    assert inserted == []


def test_palmer_skipped_when_gdd_above_upper(monkeypatch):
    mod = importlib.import_module("services.alert_engine")
    supabase, inserted = _fake_supabase()
    redis, _ = _fake_redis()
    monkeypatch.setattr(mod, "_get_service_client", lambda: supabase)
    monkeypatch.setattr(mod, "_get_redis", lambda: redis)
    monkeypatch.setattr(mod, "compute_gdd_since_jan1", _fake_gdd_500)

    rules_path = _write_rules()
    try:
        engine = mod.AlertEngine(rules_path=rules_path)
        fired = asyncio.run(engine.run_for_farmer(
            farmer_id="farmer-1",
            county_fips="05001",
            primary_crops=["soybeans"],
            language="en",
        ))
    finally:
        os.unlink(rules_path)

    assert fired == []


def test_palmer_fires_for_canonical_soybeans(monkeypatch):
    mod = importlib.import_module("services.alert_engine")
    supabase, inserted = _fake_supabase()
    redis, _ = _fake_redis()
    monkeypatch.setattr(mod, "_get_service_client", lambda: supabase)
    monkeypatch.setattr(mod, "_get_redis", lambda: redis)
    monkeypatch.setattr(mod, "compute_gdd_since_jan1", _fake_gdd_200)

    rules_path = _write_rules()
    try:
        engine = mod.AlertEngine(rules_path=rules_path)
        fired = asyncio.run(engine.run_for_farmer(
            farmer_id="farmer-1",
            county_fips="05001",
            primary_crops=["soybeans"],
            language="en",
        ))
    finally:
        os.unlink(rules_path)

    assert fired == ["palmer_amaranth"]
    assert inserted[0]["pest"] == "palmer_amaranth"


def test_palmer_fires_for_legacy_soybean_alias(monkeypatch):
    mod = importlib.import_module("services.alert_engine")
    supabase, inserted = _fake_supabase()
    redis, _ = _fake_redis()
    monkeypatch.setattr(mod, "_get_service_client", lambda: supabase)
    monkeypatch.setattr(mod, "_get_redis", lambda: redis)
    monkeypatch.setattr(mod, "compute_gdd_since_jan1", _fake_gdd_200)

    rules_path = _write_rules()
    try:
        engine = mod.AlertEngine(rules_path=rules_path)
        fired = asyncio.run(engine.run_for_farmer(
            farmer_id="farmer-1",
            county_fips="05001",
            primary_crops=["soybean"],
            language="en",
        ))
    finally:
        os.unlink(rules_path)

    assert fired == ["palmer_amaranth"]
    assert inserted[0]["pest"] == "palmer_amaranth"


def test_rww_skipped_without_recent_flood(monkeypatch):
    mod = importlib.import_module("services.alert_engine")
    supabase, inserted = _fake_supabase()
    redis, _ = _fake_redis()
    monkeypatch.setattr(mod, "_get_service_client", lambda: supabase)
    monkeypatch.setattr(mod, "_get_redis", lambda: redis)
    monkeypatch.setattr(mod, "compute_gdd_since_jan1", _fake_gdd_200)

    rules_path = _write_rules()
    try:
        engine = mod.AlertEngine(rules_path=rules_path)
        fired = asyncio.run(engine.run_for_farmer(
            farmer_id="farmer-1",
            county_fips="05001",
            primary_crops=["rice"],
            language="en",
            rice_fields=[],
        ))
    finally:
        os.unlink(rules_path)

    assert fired == []
    assert inserted == []


def test_rww_skipped_when_flood_window_is_old(monkeypatch):
    mod = importlib.import_module("services.alert_engine")
    supabase, inserted = _fake_supabase()
    redis, _ = _fake_redis()
    monkeypatch.setattr(mod, "_get_service_client", lambda: supabase)
    monkeypatch.setattr(mod, "_get_redis", lambda: redis)
    monkeypatch.setattr(mod, "compute_gdd_since_jan1", _fake_gdd_200)

    rules_path = _write_rules()
    try:
        engine = mod.AlertEngine(rules_path=rules_path)
        fired = asyncio.run(engine.run_for_farmer(
            farmer_id="farmer-1",
            county_fips="05001",
            primary_crops=["rice"],
            language="en",
            rice_fields=_rice_fields(21),
        ))
    finally:
        os.unlink(rules_path)

    assert fired == []
    assert inserted == []


def _fake_redis_exists_raises():
    class FakeRedis:
        def exists(self, key):
            raise RuntimeError("redis down")
        def set(self, key, val, ex=None):
            pass
    return FakeRedis()


def _fake_redis_capturing_ttl():
    captured = {}

    class FakeRedis:
        def exists(self, key):
            return 0
        def set(self, key, val, ex=None):
            captured[key] = ex
    return FakeRedis(), captured


def test_alert_skipped_when_dedup_check_errors(monkeypatch):
    # F8: when redis.exists raises, skip the alert (don't fall through to an
    # insert that would duplicate on every scheduler run during an outage).
    mod = importlib.import_module("services.alert_engine")
    supabase, inserted = _fake_supabase()
    monkeypatch.setattr(mod, "_get_service_client", lambda: supabase)
    monkeypatch.setattr(mod, "_get_redis", lambda: _fake_redis_exists_raises())
    monkeypatch.setattr(mod, "compute_gdd_since_jan1", _fake_gdd_200)

    rules_path = _write_rules()
    try:
        engine = mod.AlertEngine(rules_path=rules_path)
        fired = asyncio.run(engine.run_for_farmer(
            farmer_id="farmer-1", county_fips="05001",
            primary_crops=["rice"], language="en", rice_fields=_rice_fields(7),
        ))
    finally:
        os.unlink(rules_path)

    assert fired == []
    assert inserted == []


def test_dedup_ttl_covers_flood_window(monkeypatch):
    # F9: a 14-day flood-window rule must dedup for ≥14 days, else it re-fires
    # mid-window (the old fixed 5-day TTL was too short).
    mod = importlib.import_module("services.alert_engine")
    supabase, inserted = _fake_supabase()
    redis, captured = _fake_redis_capturing_ttl()
    monkeypatch.setattr(mod, "_get_service_client", lambda: supabase)
    monkeypatch.setattr(mod, "_get_redis", lambda: redis)
    monkeypatch.setattr(mod, "compute_gdd_since_jan1", _fake_gdd_200)

    rules_path = _write_rules()
    try:
        engine = mod.AlertEngine(rules_path=rules_path)
        asyncio.run(engine.run_for_farmer(
            farmer_id="farmer-1", county_fips="05001",
            primary_crops=["rice"], language="en", rice_fields=_rice_fields(7),
        ))
    finally:
        os.unlink(rules_path)

    ttl = captured["alert:farmer-1:rice_water_weevil"]
    assert ttl >= 14 * 24 * 60 * 60


def test_real_alert_rules_use_profile_crop_keys():
    rules_path = BACKEND_DIR / "data" / "alert_rules.json"
    rules = json.loads(rules_path.read_text())
    profile_crop_keys = {"rice", "soybeans", "poultry"}
    assert all(rule["crop"] in profile_crop_keys for rule in rules)
