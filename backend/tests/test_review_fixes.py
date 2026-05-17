import asyncio
import importlib
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from jose import JWTError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_query_request_session_history_uses_isolated_lists():
    query_router = importlib.import_module("routers.query")

    first = query_router.QueryRequest(message="rice problem")
    second = query_router.QueryRequest(message="soybean problem")

    first.session_history.append({"role": "user", "content": "hello"})

    assert second.session_history == []


def test_register_request_primary_crops_uses_isolated_lists():
    user_models = importlib.import_module("models.user")

    first = user_models.RegisterRequest(
        email="a@example.com",
        password="password1",
        full_name="A Farmer",
        county_fips="05001",
    )
    second = user_models.RegisterRequest(
        email="b@example.com",
        password="password1",
        full_name="B Farmer",
        county_fips="05003",
    )

    first.primary_crops.append("rice")

    assert second.primary_crops == []


def test_decode_token_returns_generic_client_error(monkeypatch, caplog):
    auth_service = importlib.import_module("services.auth")

    def fail_header(_token):
        raise JWTError("signature detail should stay server-side")

    monkeypatch.setattr(auth_service.jwt, "get_unverified_header", fail_header)

    with pytest.raises(HTTPException) as exc_info:
        auth_service.decode_token("bad-token")

    assert exc_info.value.detail == "Invalid token"
    assert "signature detail should stay server-side" in caplog.text


def test_admin_metrics_uses_rpc(monkeypatch):
    admin_service = importlib.import_module("services.admin")
    calls = []
    expected = {"totals": {"registered_users": 1}}

    class RpcResult:
        data = expected

    class Client:
        def rpc(self, name):
            calls.append(name)
            return self

        def execute(self):
            return RpcResult()

    monkeypatch.setattr(admin_service, "_get_service_client", lambda: Client())

    assert admin_service.get_dashboard_metrics() == expected
    assert calls == ["get_admin_dashboard_metrics"]


def test_login_rate_limit_returns_429_after_10_attempts(monkeypatch):
    auth_router = importlib.import_module("routers.auth")
    call_count = [0]

    def fake_rate_limit(key, limit, window):
        call_count[0] += 1
        return False, 0  # False = not allowed (over limit)

    monkeypatch.setattr(auth_router, "rate_limit_hit", fake_rate_limit)

    login_body = auth_router.LoginRequest(email="farmer@test.com", password="pw")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth_router.login(login_body))

    assert exc_info.value.status_code == 429
    assert call_count[0] == 1


def test_query_stream_emits_error_payload_and_logs_persistence(monkeypatch, caplog):
    query_router = importlib.import_module("routers.query")

    async def classify(_message):
        return "IN_SCOPE"

    class Result:
        def model_dump(self):
            return {"problem_summary": "summary"}

    async def run_rag_query(**_kwargs):
        return Result(), []

    def failing_save(*_args, **_kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(query_router, "classify_query", classify)
    monkeypatch.setattr(query_router, "run_rag_query", run_rag_query)
    monkeypatch.setattr(query_router, "save_message", failing_save)
    monkeypatch.setattr(query_router, "get_profile", lambda _sub: {"county_fips": "05001"})
    monkeypatch.setattr(query_router, "rate_limit_hit", lambda *_args: (True, 1))

    req = query_router.QueryRequest(
        message="What is wrong with my rice?",
        session_id="session-id",
    )
    response = asyncio.run(query_router.query(req, {"sub": "user-id"}))

    async def read_body():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return b"".join(c if isinstance(c, bytes) else c.encode() for c in chunks)

    body = asyncio.run(read_body()).decode()

    assert '"advisory"' in body
    assert "Failed to persist advisory query response" in caplog.text
