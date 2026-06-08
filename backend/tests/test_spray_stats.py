import importlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _fake_select_client(return_data):
    class FakeResult:
        data = return_data

    class FakeChain:
        def select(self, *a):
            return self
        def execute(self):
            return FakeResult()

    class FakeClient:
        def table(self, _name):
            return FakeChain()

    return FakeClient()


def test_aggregate_gate_stats_empty(monkeypatch):
    svc = importlib.import_module("services.spray_stats")
    monkeypatch.setattr(svc, "_get_service_client", lambda: _fake_select_client([]))

    res = svc.aggregate_gate_stats()
    assert res["total_records"] == 0
    for gate in ["A", "B", "C", "D"]:
        assert res["gates"][gate] == {"pass": 0, "fail": 0, "needs_confirmation": 0}


def test_aggregate_gate_stats_counts(monkeypatch):
    svc = importlib.import_module("services.spray_stats")
    mock_data = [
        {
            "gates": [
                {"gate": "A", "status": "pass"},
                {"gate": "B", "status": "needs_confirmation"},
                {"gate": "C", "status": "fail"},
                {"gate": "D", "status": "pass"},
            ]
        },
        {
            "gates": [
                {"gate": "A", "status": "pass"},
                {"gate": "B", "status": "pass"},
                {"gate": "C", "status": "needs_confirmation"},
                {"gate": "D", "status": "pass"},
            ]
        },
    ]
    monkeypatch.setattr(svc, "_get_service_client", lambda: _fake_select_client(mock_data))

    res = svc.aggregate_gate_stats()
    assert res["total_records"] == 2
    assert res["gates"]["A"] == {"pass": 2, "fail": 0, "needs_confirmation": 0}
    assert res["gates"]["B"] == {"pass": 1, "fail": 0, "needs_confirmation": 1}
    assert res["gates"]["C"] == {"pass": 0, "fail": 1, "needs_confirmation": 1}
    assert res["gates"]["D"] == {"pass": 2, "fail": 0, "needs_confirmation": 0}
