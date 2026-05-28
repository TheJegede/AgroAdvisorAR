# backend/tests/test_alerts_router.py
import importlib
import sys
import asyncio
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _fake_alert_row(pest="rice_water_weevil"):
    return {
        "id": "alert-uuid-1",
        "farmer_id": "farmer-uuid-1",
        "pest": pest,
        "gdd_value": 175.5,
        "message_en": "RWW alert EN",
        "message_es": "RWW alert ES",
        "fired_at": "2026-05-27T11:00:00+00:00",
        "dismissed_at": None,
    }


def _fake_supabase_chain(rows):
    class FakeResult:
        data = rows

    class FakeChain:
        def select(self, *a): return self
        def eq(self, *a): return self
        def is_(self, *a): return self
        def order(self, *a, **kw): return self
        def maybe_single(self): return self
        def update(self, *a): return self
        def execute(self): return FakeResult()

    class FakeClient:
        def table(self, _): return FakeChain()

    return FakeClient()


def test_list_alerts_returns_message_in_spanish(monkeypatch):
    mod = importlib.import_module("routers.alerts")
    monkeypatch.setattr(mod, "_get_service_client", lambda: _fake_supabase_chain([_fake_alert_row()]))
    monkeypatch.setattr(mod, "get_profile", lambda uid: {"language": "es"})

    user = {"sub": "farmer-uuid-1"}
    result = asyncio.run(mod.list_alerts(user))
    assert result[0].message == "RWW alert ES"
    assert result[0].pest == "rice_water_weevil"
    assert result[0].id == "alert-uuid-1"


def test_list_alerts_defaults_to_english(monkeypatch):
    mod = importlib.import_module("routers.alerts")
    monkeypatch.setattr(mod, "_get_service_client", lambda: _fake_supabase_chain([_fake_alert_row()]))
    monkeypatch.setattr(mod, "get_profile", lambda uid: {"language": "en"})

    user = {"sub": "farmer-uuid-1"}
    result = asyncio.run(mod.list_alerts(user))
    assert result[0].message == "RWW alert EN"


def test_list_alerts_returns_empty_when_no_alerts(monkeypatch):
    mod = importlib.import_module("routers.alerts")
    monkeypatch.setattr(mod, "_get_service_client", lambda: _fake_supabase_chain([]))
    monkeypatch.setattr(mod, "get_profile", lambda uid: {"language": "en"})

    user = {"sub": "farmer-uuid-1"}
    result = asyncio.run(mod.list_alerts(user))
    assert result == []


def test_dismiss_alert_sets_dismissed_at(monkeypatch):
    mod = importlib.import_module("routers.alerts")
    updated = []

    class FakeResult:
        data = {"id": "alert-uuid-1", "farmer_id": "farmer-uuid-1"}

    class FakeChain:
        def select(self, *a): return self
        def eq(self, *a): return self
        def maybe_single(self): return self
        def update(self, patch):
            updated.append(patch)
            return self
        def execute(self): return FakeResult()

    class FakeClient:
        def table(self, _): return FakeChain()

    monkeypatch.setattr(mod, "_get_service_client", lambda: FakeClient())

    user = {"sub": "farmer-uuid-1"}
    # Should complete without raising (204 = None return)
    asyncio.run(mod.dismiss_alert("alert-uuid-1", user))
    assert len(updated) == 1
    assert "dismissed_at" in updated[0]


def test_dismiss_alert_raises_404_for_wrong_farmer(monkeypatch):
    mod = importlib.import_module("routers.alerts")

    class FakeResult:
        data = {"id": "alert-uuid-1", "farmer_id": "other-farmer"}

    class FakeChain:
        def select(self, *a): return self
        def eq(self, *a): return self
        def maybe_single(self): return self
        def execute(self): return FakeResult()

    class FakeClient:
        def table(self, _): return FakeChain()

    monkeypatch.setattr(mod, "_get_service_client", lambda: FakeClient())

    import pytest
    user = {"sub": "farmer-uuid-1"}
    with pytest.raises(Exception) as exc_info:
        asyncio.run(mod.dismiss_alert("alert-uuid-1", user))
    assert "404" in str(exc_info.value) or "not found" in str(exc_info.value).lower()
