# backend/tests/test_sessions_deletion.py
import importlib
import sys
from pathlib import Path
import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _fake_client_delete(return_data):
    class FakeResult:
        data = return_data

    class FakeChain:
        def delete(self): return self
        def eq(self, *a): return self
        def execute(self): return FakeResult()

    class FakeClient:
        def table(self, _name):
            return FakeChain()

    return FakeClient()


def test_delete_session_success(monkeypatch):
    session_service = importlib.import_module("services.session")
    monkeypatch.setattr(
        session_service, "_get_service_client",
        lambda: _fake_client_delete([{"id": "session-1"}]),
    )
    result = session_service.delete_session("session-1", "user-1")
    assert result is True


def test_delete_session_not_found_or_unauthorized(monkeypatch):
    session_service = importlib.import_module("services.session")
    monkeypatch.setattr(
        session_service, "_get_service_client",
        lambda: _fake_client_delete([]),
    )
    result = session_service.delete_session("session-1", "user-1")
    assert result is False


def test_remove_session_router_success(monkeypatch):
    router_mod = importlib.import_module("routers.sessions")
    monkeypatch.setattr(
        router_mod, "delete_session",
        lambda sid, uid: True,
    )
    # The endpoint returns status_code=204 which returns None or empty
    result = router_mod.remove_session("session-1", user={"sub": "user-1"})
    assert result is None


def test_remove_session_router_404(monkeypatch):
    router_mod = importlib.import_module("routers.sessions")
    monkeypatch.setattr(
        router_mod, "delete_session",
        lambda sid, uid: False,
    )
    with pytest.raises(HTTPException) as exc_info:
        router_mod.remove_session("session-1", user={"sub": "user-1"})
    assert exc_info.value.status_code == 404
    assert "Session not found" in exc_info.value.detail
