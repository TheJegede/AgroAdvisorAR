# backend/tests/test_session_ownership.py
"""F1 — add_message must verify session ownership before writing, to close the
IDOR write where a client-supplied session_id let one user poison another's chat."""
import importlib
import sys
from pathlib import Path
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class _Recorder:
    """Captures inserts/updates and serves a configurable ownership row."""

    def __init__(self, owned: bool):
        self._owned = owned
        self.inserts: list[tuple[str, dict]] = []
        self.updates: list[tuple[str, dict]] = []

    def table(self, name):
        return _Chain(self, name)


class _Result:
    def __init__(self, data):
        self.data = data


class _Chain:
    def __init__(self, rec: _Recorder, name: str):
        self._rec = rec
        self._name = name
        self._op = None
        self._payload = None

    # ownership read
    def select(self, *_a):
        self._op = "select"
        return self

    def eq(self, *_a):
        return self

    def maybe_single(self):
        return self

    # writes
    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def update(self, row):
        self._op = "update"
        self._payload = row
        return self

    def execute(self):
        if self._op == "select":
            return _Result({"id": "session-1"} if self._rec._owned else None)
        if self._op == "insert":
            self._rec.inserts.append((self._name, self._payload))
            return _Result([{"id": "msg-1", **self._payload}])
        if self._op == "update":
            self._rec.updates.append((self._name, self._payload))
            return _Result([{"id": "session-1"}])
        return _Result(None)


def test_add_message_rejects_non_owned_session(monkeypatch):
    session_service = importlib.import_module("services.session")
    rec = _Recorder(owned=False)
    monkeypatch.setattr(session_service, "_get_service_client", lambda: rec)

    with pytest.raises(session_service.SessionOwnershipError):
        session_service.add_message(
            "victim-session", "attacker", "user", "hi", "text",
        )

    # No row written into chat_messages, no last_message_at bump.
    assert rec.inserts == []
    assert rec.updates == []


def test_add_message_writes_for_owned_session(monkeypatch):
    session_service = importlib.import_module("services.session")
    rec = _Recorder(owned=True)
    monkeypatch.setattr(session_service, "_get_service_client", lambda: rec)
    # _assert_insert reads result.data; the recorder returns a populated list.
    monkeypatch.setattr(session_service, "_assert_insert", lambda *a, **k: None)

    row = session_service.add_message(
        "session-1", "owner", "user", "hi", "text",
    )
    assert row["id"] == "msg-1"
    assert any(name == "chat_messages" for name, _ in rec.inserts)
    assert any(name == "chat_sessions" for name, _ in rec.updates)
