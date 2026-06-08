import importlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _fake_insert_client(sink):
    class FakeResult:
        data = [{"id": "rec-1", "farmer_id": "farmer-1"}]

    class FakeTable:
        def insert(self, row):
            sink.append(row)
            return self
        def execute(self):
            return FakeResult()

    class FakeClient:
        def table(self, _name):
            return FakeTable()

    return FakeClient()


def _fake_select_client(return_data, captured_eqs):
    class FakeResult:
        data = return_data

    class FakeChain:
        def select(self, *a): return self
        def eq(self, col, val):
            captured_eqs.append((col, val))
            return self
        def order(self, *a, **kw): return self
        def limit(self, *a): return self
        def maybe_single(self): return self
        def execute(self): return FakeResult()

    class FakeClient:
        def table(self, _name):
            return FakeChain()

    return FakeClient()


def test_create_record_stamps_farmer_id_from_arg(monkeypatch):
    svc = importlib.import_module("services.spray_record")
    sink = []
    monkeypatch.setattr(svc, "_get_service_client", lambda: _fake_insert_client(sink))
    payload = {
        "lat": 34.7, "lon": -91.8, "product": "engenia",
        "applied_at": "2026-06-08T09:00:00", "overall_status": "needs_confirmation",
        "rule_version": "2026-AR-OTT", "gates": [], "attestation": {},
        "weather_json": None, "farmer_id": "attacker-supplied",
    }
    svc.create_record("farmer-1", payload)
    # farmer_id is stamped from the arg, never the payload.
    assert sink[0]["farmer_id"] == "farmer-1"


def test_get_record_filters_by_id_and_farmer(monkeypatch):
    svc = importlib.import_module("services.spray_record")
    eqs = []
    monkeypatch.setattr(
        svc, "_get_service_client", lambda: _fake_select_client({"id": "rec-1"}, eqs)
    )
    svc.get_record("rec-1", "farmer-1")
    assert ("id", "rec-1") in eqs
    assert ("farmer_id", "farmer-1") in eqs


def test_get_record_returns_none_for_foreign(monkeypatch):
    svc = importlib.import_module("services.spray_record")
    monkeypatch.setattr(
        svc, "_get_service_client", lambda: _fake_select_client(None, [])
    )
    assert svc.get_record("rec-1", "other-farmer") is None


def test_no_mutate_or_delete_surface():
    svc = importlib.import_module("services.spray_record")
    assert not hasattr(svc, "update_record")
    assert not hasattr(svc, "delete_record")
