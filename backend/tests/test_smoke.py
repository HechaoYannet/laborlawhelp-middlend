from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.config import settings
from app.core.store import InMemoryStore, store
from app.main import app


@pytest.fixture(autouse=True)
def reset_runtime_state() -> Generator[None, None, None]:
    old_auth_mode = settings.auth_mode
    old_storage_backend = settings.storage_backend
    old_rate = settings.rate_limit_per_minute
    old_oh_mock = settings.oh_use_mock

    settings.auth_mode = "anonymous"
    settings.storage_backend = "memory"
    settings.rate_limit_per_minute = 20
    settings.oh_use_mock = True

    if isinstance(store, InMemoryStore):
        store.cases.clear()
        store.sessions.clear()
        store.messages.clear()
        store.session_locks.clear()
        store.stream_seq.clear()

    rate_limit._RATE_COUNTER.clear()

    yield

    settings.auth_mode = old_auth_mode
    settings.storage_backend = old_storage_backend
    settings.rate_limit_per_minute = old_rate
    settings.oh_use_mock = old_oh_mock


def _create_case_and_session(client: TestClient, token: str) -> tuple[str, str]:
    headers = {"X-Anonymous-Token": token}
    case_resp = client.post("/api/v1/cases", json={"title": "t", "region_code": "xian"}, headers=headers)
    assert case_resp.status_code == 201
    case_id = case_resp.json()["id"]

    session_resp = client.post(f"/api/v1/cases/{case_id}/sessions", headers=headers)
    assert session_resp.status_code == 201
    return case_id, session_resp.json()["id"]


def test_main_flow_stream_events() -> None:
    client = TestClient(app)
    headers = {"X-Anonymous-Token": "anon-test"}
    _, session_id = _create_case_and_session(client, "anon-test")

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat",
        json={"message": "被辞退了", "client_seq": 1, "attachments": []},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        payload = "".join(response.iter_text())

    assert "event: message_start" in payload
    assert "event: content_delta" in payload
    assert "event: tool_call" in payload
    assert "event: tool_result" in payload
    assert "event: final" in payload
    assert "event: message_end" in payload


def test_cross_owner_forbidden() -> None:
    client = TestClient(app)
    case_id, _ = _create_case_and_session(client, "anon-owner-a")

    forbidden_resp = client.get(f"/api/v1/cases/{case_id}", headers={"X-Anonymous-Token": "anon-owner-b"})
    assert forbidden_resp.status_code == 403
    assert forbidden_resp.json()["code"] == "FORBIDDEN"


def test_end_session_then_chat_returns_410() -> None:
    client = TestClient(app)
    headers = {"X-Anonymous-Token": "anon-end"}
    _, session_id = _create_case_and_session(client, "anon-end")

    end_resp = client.patch(f"/api/v1/sessions/{session_id}/end", headers=headers)
    assert end_resp.status_code == 200

    response = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        json={"message": "再次发言", "client_seq": 1, "attachments": []},
        headers=headers,
    )
    assert response.status_code == 410
    body = response.json()

    assert body["code"] == "ANONYMOUS_SESSION_EXPIRED"


def test_messages_endpoint_contains_user_and_assistant() -> None:
    client = TestClient(app)
    headers = {"X-Anonymous-Token": "anon-msg"}
    _, session_id = _create_case_and_session(client, "anon-msg")

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat",
        json={"message": "请给建议", "client_seq": 1, "attachments": []},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        _ = "".join(response.iter_text())

    messages_resp = client.get(f"/api/v1/sessions/{session_id}/messages", headers=headers)
    assert messages_resp.status_code == 200
    data = messages_resp.json()
    roles = [m["role"] for m in data]
    assert "user" in roles
    assert "assistant" in roles


def test_rate_limit_enforced_on_chat() -> None:
    settings.rate_limit_per_minute = 1
    client = TestClient(app)
    headers = {"X-Anonymous-Token": "anon-rate"}
    _, session_id = _create_case_and_session(client, "anon-rate")

    first = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        json={"message": "第一次", "client_seq": 1, "attachments": []},
        headers=headers,
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/v1/sessions/{session_id}/chat",
        json={"message": "第二次", "client_seq": 2, "attachments": []},
        headers=headers,
    )
    assert second.status_code == 429
    assert second.json()["code"] == "RATE_LIMITED"


def test_jwt_mode_requires_bearer_and_allows_login_refresh() -> None:
    settings.auth_mode = "jwt"
    client = TestClient(app)

    no_auth = client.post("/api/v1/cases", json={"title": "jwt", "region_code": "xian"})
    assert no_auth.status_code == 401
    assert no_auth.json()["code"] == "UNAUTHORIZED"

    login = client.post("/api/v1/auth/sms/login", json={"phone": "13800000000", "code": "123456"})
    assert login.status_code == 200
    access_token = login.json()["access_token"]
    refresh_token = login.json()["refresh_token"]

    auth_headers = {"Authorization": f"Bearer {access_token}"}
    create_case_resp = client.post("/api/v1/cases", json={"title": "jwt", "region_code": "xian"}, headers=auth_headers)
    assert create_case_resp.status_code == 201
    assert create_case_resp.json()["owner_type"] == "user"

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200
    assert refresh_resp.json()["access_token"]


def test_refresh_rejects_invalid_token() -> None:
    client = TestClient(app)
    bad_refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": "bad-token"})
    assert bad_refresh.status_code == 401
    assert bad_refresh.json()["code"] == "UNAUTHORIZED"
