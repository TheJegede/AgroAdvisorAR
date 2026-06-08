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
    },
}

WEATHER_OK = {
    "available": True,
    "wind_speed_mph": 6.0,
    "temp_f": 78.0,
    "precip_next_48h_in": 0.0,
    "inversion": {"risk": "low", "is_estimate": True, "reason": "x"},
}


def _body(product="engenia", at=datetime(2026, 5, 1, 9, 0)):
    from models.spray import SprayCheckRequest
    return SprayCheckRequest(lat=34.7, lon=-91.8, product=product, at=at)


def test_check_returns_gates_a_and_c(monkeypatch):
    router_mod = importlib.import_module("routers.dicamba")
    monkeypatch.setattr(router_mod, "resolve_rules", lambda on_date: RULES)
    monkeypatch.setattr(
        router_mod, "fetch_forecast_conditions", AsyncMock(return_value=WEATHER_OK)
    )

    resp = asyncio.run(router_mod.check_spray(_body(), user=FAKE_USER))
    assert {g.gate for g in resp.gates} == {"A", "B", "C"}
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
