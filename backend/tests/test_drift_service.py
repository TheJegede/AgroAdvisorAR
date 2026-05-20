import importlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _fake_client_insert(expected_row_id, inserted_rows_sink):
    class FakeResult:
        data = [{"id": expected_row_id, "farmer_id": "farmer-1"}]

    class FakeTable:
        def insert(self, row):
            inserted_rows_sink.append(row)
            return self
        def execute(self):
            return FakeResult()

    class FakeClient:
        def table(self, _name):
            return FakeTable()

    return FakeClient()


def _fake_client_select(return_data):
    class FakeResult:
        data = return_data

    class FakeChain:
        def select(self, *a): return self
        def eq(self, *a): return self
        def order(self, *a, **kw): return self
        def maybe_single(self): return self
        def gte(self, *a): return self
        def lte(self, *a): return self
        def execute(self): return FakeResult()

    class FakeClient:
        def table(self, _name):
            return FakeChain()

    return FakeClient()


def test_create_report_populates_weather_fields(monkeypatch):
    drift_service = importlib.import_module("services.drift_service")
    inserted = []
    monkeypatch.setattr(
        drift_service, "_get_service_client",
        lambda: _fake_client_insert("uuid-1", inserted),
    )

    data = {
        "incident_date": "2024-07-14",
        "county_fips": "05055",
        "affected_crop": "soybean",
        "affected_acres": 50.0,
        "suspected_herbicide": "dicamba",
        "symptoms_description": "Cupping",
        "neighboring_applicator": None,
        "photos_attached": False,
        "aspb_submitted": False,
    }
    weather = {
        "available": True,
        "hourly_summary": {
            "wind_speed_mph_avg": 8.2,
            "wind_direction_label": "S",
            "temp_f_at_noon": 91.4,
        },
    }

    result = drift_service.create_report("farmer-1", data, weather)

    assert result["id"] == "uuid-1"
    assert len(inserted) == 1
    row = inserted[0]
    assert row["wind_speed_mph"] == 8.2
    assert row["wind_direction"] == "S"
    assert row["temp_at_time_f"] == 91.4
    assert row["farmer_id"] == "farmer-1"


def test_create_report_handles_unavailable_weather(monkeypatch):
    drift_service = importlib.import_module("services.drift_service")
    inserted = []
    monkeypatch.setattr(
        drift_service, "_get_service_client",
        lambda: _fake_client_insert("uuid-2", inserted),
    )

    data = {
        "incident_date": "2024-07-14",
        "county_fips": "05055",
        "affected_crop": None,
        "affected_acres": None,
        "suspected_herbicide": "dicamba",
        "symptoms_description": None,
        "neighboring_applicator": None,
        "photos_attached": False,
        "aspb_submitted": False,
    }

    result = drift_service.create_report("farmer-1", data, {"available": False})

    assert result["id"] == "uuid-2"
    row = inserted[0]
    assert row.get("wind_speed_mph") is None
    assert row.get("weather_json") is None


def test_get_report_returns_none_when_not_found(monkeypatch):
    drift_service = importlib.import_module("services.drift_service")
    monkeypatch.setattr(
        drift_service, "_get_service_client",
        lambda: _fake_client_select(None),
    )

    result = drift_service.get_report("non-existent", "farmer-1")
    assert result is None


def test_list_reports_returns_empty_list(monkeypatch):
    drift_service = importlib.import_module("services.drift_service")
    monkeypatch.setattr(
        drift_service, "_get_service_client",
        lambda: _fake_client_select([]),
    )

    result = drift_service.list_reports("farmer-1")
    assert result == []


def test_list_all_reports_returns_all(monkeypatch):
    drift_service = importlib.import_module("services.drift_service")
    monkeypatch.setattr(
        drift_service, "_get_service_client",
        lambda: _fake_client_select([{"id": "r1"}, {"id": "r2"}]),
    )

    result = drift_service.list_all_reports()
    assert len(result) == 2
