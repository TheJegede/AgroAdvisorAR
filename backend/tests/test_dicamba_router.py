import asyncio
import importlib
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.spray_rules import RulesNotFoundError  # noqa: E402

FAKE_USER = {"sub": "farmer-uuid-1"}

RULES = {
    "rule_version": "2026-AR-OTT",
    "season_window": {"start": "2026-04-15", "end": "2026-06-30"},
    "buffers_ft": {
        "research_station": 5280,
        "organic_specialty": 2640,
        "non_tolerant_crop": 1320,
    },
    "approved_products": [{"id": "engenia"}, {"id": "xtendimax"}, {"id": "tavium"}],
    "weather_thresholds": {
        "wind_mph": {"min": 3.0, "max": 10.0},
        "air_temp_f": {"min": 50.0, "max": 91.0},
        "rain_free_hours_required": 48,
        "downwind_half_angle_deg": 45,
        "soil_moisture_max": 0.45,
    },
}

WEATHER_OK = {
    "available": True,
    "wind_speed_mph": 6.0,
    "temp_f": 78.0,
    "precip_next_48h_in": 0.0,
    "soil_moisture_0_1cm": 0.2,
    "inversion": {"risk": "low", "is_estimate": True, "reason": "x", "reason_es": "y"},
}


def _body(product="engenia", at=datetime(2026, 5, 1, 9, 0), attestation=None):
    from models.spray import ApplicatorAttestation, SprayCheckRequest
    return SprayCheckRequest(
        lat=34.7,
        lon=-91.8,
        product=product,
        at=at,
        attestation=attestation or ApplicatorAttestation(),
    )


def _legal_attestation():
    from models.spray import ApplicatorAttestation
    return ApplicatorAttestation(license_attested=True, training_attested=True)


def test_to_central_converts_utc_to_arkansas_local():
    # July 1 01:00 UTC is still June 30 (8:00 pm CDT) in Arkansas. The Gate A
    # season-window date must be the Central date, not the UTC date. (F1)
    from datetime import timezone

    router_mod = importlib.import_module("routers.dicamba")
    utc_dt = datetime(2026, 7, 1, 1, 0, tzinfo=timezone.utc)
    local = router_mod._to_central(utc_dt)
    assert local.date().isoformat() == "2026-06-30"


def test_to_central_passthrough_for_naive():
    # A naive datetime is assumed already-local — no shift.
    router_mod = importlib.import_module("routers.dicamba")
    naive = datetime(2026, 6, 8, 9, 0)
    assert router_mod._to_central(naive) == naive


def test_check_converts_at_to_central_before_rules(monkeypatch):
    # An incoming UTC `at` must reach resolve_rules / weather as Arkansas local. (F1)
    from datetime import timezone

    router_mod = importlib.import_module("routers.dicamba")
    seen = {}

    def _capture_rules(on_date):
        seen["rules_date"] = on_date
        return RULES

    fake_fetch = AsyncMock(return_value=WEATHER_OK)
    monkeypatch.setattr(router_mod, "resolve_rules", _capture_rules)
    monkeypatch.setattr(router_mod, "fetch_forecast_conditions", fake_fetch)

    utc_at = datetime(2026, 7, 1, 1, 0, tzinfo=timezone.utc)  # = 2026-06-30 CDT
    asyncio.run(router_mod.check_spray(_body(at=utc_at), user=FAKE_USER))

    assert seen["rules_date"].isoformat() == "2026-06-30"
    weather_at = fake_fetch.call_args.args[2]
    assert weather_at.date().isoformat() == "2026-06-30"


def test_check_returns_gates_a_and_c(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")
    monkeypatch.setattr(router_mod, "resolve_rules", lambda on_date: RULES)
    monkeypatch.setattr(
        router_mod, "fetch_forecast_conditions", AsyncMock(return_value=WEATHER_OK)
    )

    resp = asyncio.run(router_mod.check_spray(_body(), user=FAKE_USER))
    assert {g.gate for g in resp.gates} == {"A", "B", "C", "D"}
    assert resp.rule_version == "2026-AR-OTT"
    assert resp.weather_available is True


def test_list_stations_returns_seed_list():
    router_mod = importlib.import_module("routers.dicamba")
    stations = asyncio.run(router_mod.list_stations(user=FAKE_USER))
    assert len(stations) >= 5
    # Function returns raw dicts; FastAPI coerces to ResearchStation at the response layer.
    assert all({"id", "name", "lat", "lon"} <= set(s) for s in stations)


def test_check_422_when_no_rules_for_date(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")

    def _raise(on_date):
        raise RulesNotFoundError("none")

    monkeypatch.setattr(router_mod, "resolve_rules", _raise)
    monkeypatch.setattr(
        router_mod, "fetch_forecast_conditions", AsyncMock(return_value=WEATHER_OK)
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(router_mod.check_spray(_body(), user=FAKE_USER))
    assert exc_info.value.status_code == 422


def test_check_uses_no_client_supplied_owner():
    # Stateless endpoint: the request schema carries no owner field, so an
    # injected farmer_id cannot be trusted/echoed (defense vs IDOR by design).
    from models.spray import SprayCheckRequest
    req = SprayCheckRequest(
        lat=34.7, lon=-91.8, product="engenia",
        at=datetime(2026, 5, 1, 9, 0), farmer_id="attacker",
    )
    assert not hasattr(req, "farmer_id")


def test_check_weather_unavailable_returns_gate_a_and_needs_confirmation_gate_c(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")
    monkeypatch.setattr(router_mod, "resolve_rules", lambda on_date: RULES)
    monkeypatch.setattr(
        router_mod, "fetch_forecast_conditions",
        AsyncMock(return_value={"available": False}),
    )

    resp = asyncio.run(router_mod.check_spray(_body(), user=FAKE_USER))
    gate_a = next(g for g in resp.gates if g.gate == "A")
    gate_c = next(g for g in resp.gates if g.gate == "C")
    assert gate_a.status == "pass"
    assert gate_c.status == "needs_confirmation"
    assert resp.weather_available is False


def test_create_record_persists_and_uses_authenticated_owner(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")
    monkeypatch.setattr(router_mod, "resolve_rules", lambda on_date: RULES)
    monkeypatch.setattr(
        router_mod, "fetch_forecast_conditions", AsyncMock(return_value=WEATHER_OK)
    )
    monkeypatch.setattr(router_mod, "load_stations", lambda: [])
    captured = {}

    def _fake_create(farmer_id, payload):
        captured["farmer_id"] = farmer_id
        captured["payload"] = payload
        return {"id": "rec-1", "farmer_id": farmer_id, **payload}

    monkeypatch.setattr(router_mod, "create_record", _fake_create)

    rec = asyncio.run(router_mod.create_spray_record(
        _body(attestation=_legal_attestation()), user=FAKE_USER
    ))
    assert captured["farmer_id"] == FAKE_USER["sub"]
    assert captured["payload"]["rule_version"] == "2026-AR-OTT"
    assert {g["gate"] for g in captured["payload"]["gates"]} == {"A", "B", "C", "D"}
    assert captured["payload"]["attestation"]["license_attested"] is True
    assert captured["payload"]["attestation"]["training_attested"] is True
    assert rec["id"] == "rec-1"


def test_create_record_requires_license_and_training_attestations():
    router_mod = importlib.import_module("routers.dicamba")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(router_mod.create_spray_record(_body(), user=FAKE_USER))

    assert exc_info.value.status_code == 422
    assert "license" in exc_info.value.detail.lower()
    assert "training" in exc_info.value.detail.lower()


def test_check_preview_allows_missing_license_and_training(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")
    monkeypatch.setattr(router_mod, "resolve_rules", lambda on_date: RULES)
    monkeypatch.setattr(
        router_mod, "fetch_forecast_conditions", AsyncMock(return_value=WEATHER_OK)
    )
    monkeypatch.setattr(router_mod, "load_stations", lambda: [])

    resp = asyncio.run(router_mod.check_spray(_body(), user=FAKE_USER))

    assert resp.rule_version == "2026-AR-OTT"


def test_get_record_404_when_foreign(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")
    monkeypatch.setattr(router_mod, "get_record", lambda rid, fid: None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(router_mod.get_spray_record("rec-x", user=FAKE_USER))
    assert exc.value.status_code == 404


def test_list_records_uses_owner(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")
    seen = {}

    def _fake_list(fid, **kw):
        seen["fid"] = fid
        return [{"id": "rec-1"}]

    monkeypatch.setattr(router_mod, "list_records", _fake_list)
    out = asyncio.run(router_mod.list_spray_records(user=FAKE_USER))
    assert seen["fid"] == FAKE_USER["sub"]
    assert out[0]["id"] == "rec-1"


def test_get_spray_stats_admin_success(monkeypatch):
    import config
    monkeypatch.setattr(config, "ADMIN_USER_IDS", {"admin-uuid-1"})

    router_mod = importlib.import_module("routers.dicamba")
    mock_stats = {"total_records": 10, "gates": {}}
    monkeypatch.setattr(router_mod, "aggregate_gate_stats", lambda: mock_stats)

    res = asyncio.run(router_mod.get_spray_stats(admin_user={"sub": "admin-uuid-1"}))
    assert res == mock_stats


def test_get_spray_stats_non_admin_forbidden(monkeypatch):
    import config
    monkeypatch.setattr(config, "ADMIN_USER_IDS", {"admin-uuid-1"})

    from services.admin import require_admin
    with pytest.raises(HTTPException) as exc_info:
        require_admin(user={"sub": "farmer-uuid-1"})
    assert exc_info.value.status_code == 403


def test_submit_spray_feedback_success(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")

    # Mock verify_record_ownership to return True
    monkeypatch.setattr(router_mod, "verify_record_ownership", lambda rid, fid: True)

    # Mock insert_spray_feedback to return a fake feedback dict
    fake_fb = {
        "id": "fb-1",
        "record_id": "rec-1",
        "farmer_id": FAKE_USER["sub"],
        "rating": 1,
        "comment": "Nice tool!",
        "created_at": datetime(2026, 6, 8, 12, 0),
    }
    monkeypatch.setattr(router_mod, "insert_spray_feedback", lambda record_id, farmer_id, rating, comment: fake_fb)

    from models.spray_feedback import SprayFeedbackRequest
    req_body = SprayFeedbackRequest(record_id="rec-1", rating=1, comment="Nice tool!")

    res = asyncio.run(router_mod.submit_spray_feedback(req_body, user=FAKE_USER))
    assert res["id"] == "fb-1"
    assert res["record_id"] == "rec-1"
    assert res["rating"] == 1
    assert res["comment"] == "Nice tool!"
    assert "2026-06-08T12:00:00" in res["created_at"]


def test_submit_spray_feedback_foreign_record_404(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")

    # Mock verify_record_ownership to return False (foreign record)
    monkeypatch.setattr(router_mod, "verify_record_ownership", lambda rid, fid: False)

    from models.spray_feedback import SprayFeedbackRequest
    req_body = SprayFeedbackRequest(record_id="rec-2", rating=-1, comment="Bad weather data")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(router_mod.submit_spray_feedback(req_body, user=FAKE_USER))
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Record not found"
