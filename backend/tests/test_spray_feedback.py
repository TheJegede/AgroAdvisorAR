import importlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_verify_record_ownership(monkeypatch):
    svc = importlib.import_module("services.spray_feedback")

    # 1. Ownership verified
    monkeypatch.setattr(svc, "get_record", lambda rid, fid: {"id": rid, "farmer_id": fid})
    assert svc.verify_record_ownership("rec-1", "farmer-1") is True

    # 2. Ownership rejected
    monkeypatch.setattr(svc, "get_record", lambda rid, fid: None)
    assert svc.verify_record_ownership("rec-2", "farmer-2") is False


def test_insert_spray_feedback_stamps_farmer_id(monkeypatch):
    svc = importlib.import_module("services.spray_feedback")
    sink = []

    class FakeResult:
        data = [{
            "id": "fb-1",
            "record_id": "rec-1",
            "farmer_id": "farmer-1",
            "rating": 1,
            "comment": "good",
        }]

    class FakeTable:
        def insert(self, row):
            sink.append(row)
            return self
        def execute(self):
            return FakeResult()

    class FakeClient:
        def table(self, _name):
            return FakeTable()

    monkeypatch.setattr(svc, "_get_service_client", lambda: FakeClient())

    res = svc.insert_spray_feedback("rec-1", "farmer-1", 1, "good")
    assert res["id"] == "fb-1"
    assert sink[0]["farmer_id"] == "farmer-1"
    assert sink[0]["record_id"] == "rec-1"
    assert sink[0]["rating"] == 1
    assert sink[0]["comment"] == "good"


def test_spray_feedback_rls_is_append_only_for_farmers():
    migration = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "migrations"
        / "011_spray_feedback_append_only_rls.sql"
    ).read_text()

    assert 'DROP POLICY IF EXISTS "farmer_all_spray_feedback"' in migration
    assert "FOR SELECT" in migration
    assert "FOR INSERT" in migration
    assert "FOR UPDATE" not in migration
    assert "FOR DELETE" not in migration
    assert 'CREATE POLICY "admin reads all spray feedback"' in migration
