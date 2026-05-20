import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

FAKE_USER = {"sub": "farmer-uuid-1"}
FAKE_REPORT = {
    "id": "report-uuid-1",
    "farmer_id": "farmer-uuid-1",
    "incident_date": "2024-07-14",
    "county_fips": "05055",
    "weather_json": None,
}


def test_list_drift_reports_returns_list(monkeypatch):
    router_mod = importlib.import_module("routers.drift_reports")
    monkeypatch.setattr(router_mod, "list_reports", lambda farmer_id: [FAKE_REPORT])

    result = router_mod.list_drift_reports(user=FAKE_USER)
    assert result == [FAKE_REPORT]


def test_get_drift_report_404_when_not_found(monkeypatch):
    router_mod = importlib.import_module("routers.drift_reports")
    monkeypatch.setattr(router_mod, "get_report", lambda rid, fid: None)

    with pytest.raises(HTTPException) as exc_info:
        router_mod.get_drift_report("bad-id", user=FAKE_USER)

    assert exc_info.value.status_code == 404


def test_get_drift_report_returns_report(monkeypatch):
    router_mod = importlib.import_module("routers.drift_reports")
    monkeypatch.setattr(router_mod, "get_report", lambda rid, fid: FAKE_REPORT)

    result = router_mod.get_drift_report("report-uuid-1", user=FAKE_USER)
    assert result["id"] == "report-uuid-1"


def test_create_drift_report_calls_service(monkeypatch):
    router_mod = importlib.import_module("routers.drift_reports")
    monkeypatch.setattr(
        router_mod, "get_county_info",
        lambda fips: {"lat": 34.74, "lon": -91.83},
    )
    monkeypatch.setattr(
        router_mod, "fetch_historical_weather",
        AsyncMock(return_value={"available": False}),
    )
    monkeypatch.setattr(
        router_mod, "create_report",
        lambda farmer_id, data, weather: {**FAKE_REPORT, "farmer_id": farmer_id},
    )

    from routers.drift_reports import DriftReportCreate
    from datetime import date
    body = DriftReportCreate(incident_date=date(2024, 7, 14), county_fips="05055")

    result = asyncio.run(router_mod.create_drift_report(body, user=FAKE_USER))
    assert result["farmer_id"] == "farmer-uuid-1"
