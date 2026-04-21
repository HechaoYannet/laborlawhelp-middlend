from collections.abc import Generator
import json
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.adapters.openharness import OHChunk
from app.core import rate_limit
from app.core.config import settings
from app.core.errors import AppError
from app.main import app
from app.modules.storage import InMemoryStore, get_store, set_store


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

    test_store = InMemoryStore()
    set_store(test_store)

    rate_limit._RATE_COUNTER.clear()

    yield

    settings.auth_mode = old_auth_mode
    settings.storage_backend = old_storage_backend
    settings.rate_limit_per_minute = old_rate
    settings.oh_use_mock = old_oh_mock
    set_store(InMemoryStore())


def _create_case_and_session(client: TestClient, token: str) -> tuple[str, str]:
    headers = {"X-Anonymous-Token": token}
    case_resp = client.post("/api/v1/cases", json={"title": "t", "region_code": "xian"}, headers=headers)
    assert case_resp.status_code == 201
    case_id = case_resp.json()["id"]

    session_resp = client.post(f"/api/v1/cases/{case_id}/sessions", headers=headers)
    assert session_resp.status_code == 201
    session_data = session_resp.json()
    assert session_data["openharness_session_id"]
    UUID(session_data["openharness_session_id"])
    return case_id, session_data["id"]


def _parse_sse_events(payload: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for frame in payload.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        lines = frame.splitlines()
        event_line = next((line for line in lines if line.startswith("event:")), None)
        data_line = next((line for line in lines if line.startswith("data:")), None)
        if not event_line or not data_line:
            continue
        event = event_line.removeprefix("event:").strip()
        data = json.loads(data_line.removeprefix("data:").strip())
        events.append((event, data))
    return events


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

    events = _parse_sse_events(payload)
    final = next(data for event, data in events if event == "final")
    assert final["trace_id"]
    assert final["finish_reason"]

    tool_result = next(data for event, data in events if event == "tool_result")
    assert "card_type" in tool_result
    assert "card_title" in tool_result
    assert "card_payload" in tool_result
    assert "card_actions" in tool_result


def test_chat_stream_alias_has_same_event_contract() -> None:
    client = TestClient(app)
    headers = {"X-Anonymous-Token": "anon-stream"}
    _, session_id = _create_case_and_session(client, "anon-stream")

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat",
        json={"message": "被辞退了", "client_seq": 1, "attachments": []},
        headers=headers,
    ) as response_compat:
        assert response_compat.status_code == 200
        compat_payload = "".join(response_compat.iter_text())

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat/stream",
        json={"message": "被辞退了", "client_seq": 2, "attachments": [], "locale": "zh-CN"},
        headers=headers,
    ) as response_stream:
        assert response_stream.status_code == 200
        stream_payload = "".join(response_stream.iter_text())

    compat_events = [event for event, _ in _parse_sse_events(compat_payload)]
    stream_events = [event for event, _ in _parse_sse_events(stream_payload)]

    assert compat_events[0] == "message_start"
    assert stream_events[0] == "message_start"
    assert compat_events[-1] == "message_end"
    assert stream_events[-1] == "message_end"
    assert "final" in compat_events
    assert "final" in stream_events


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


def test_stream_error_event_shape_and_failed_assistant_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)
    headers = {"X-Anonymous-Token": "anon-error"}
    _, session_id = _create_case_and_session(client, "anon-error")

    async def broken_stream_run(**_: dict):
        yield OHChunk(type="text", content="开头文本")
        raise AppError(504, "OH_UPSTREAM_TIMEOUT", "OpenHarness 请求超时", retryable=True)

    monkeypatch.setattr("app.modules.chat.service.openharness_client.stream_run", broken_stream_run)

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat/stream",
        json={"message": "测试异常", "client_seq": 1, "attachments": []},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        payload = "".join(response.iter_text())

    events = _parse_sse_events(payload)
    event_names = [event for event, _ in events]
    assert event_names[0] == "message_start"
    assert event_names[-2] == "error"
    assert event_names[-1] == "message_end"

    error = next(data for event, data in events if event == "error")
    assert sorted(error.keys()) == ["code", "message", "retryable", "trace_id"]
    assert error["code"] == "OH_UPSTREAM_TIMEOUT"
    assert error["retryable"] is True

    store = get_store()
    assert isinstance(store, InMemoryStore)
    assistant_messages = [m for m in store.messages if m.session_id == session_id and m.role == "assistant"]
    assert assistant_messages
    latest = assistant_messages[-1]
    assert latest.content == ""
    assert latest.metadata is not None
    assert latest.metadata["status"] == "failed"
    assert latest.metadata["error_code"] == "OH_UPSTREAM_TIMEOUT"

    assert store.audit_logs
    latest_audit = store.audit_logs[-1]
    assert latest_audit.trace_id == error["trace_id"]
    assert latest_audit.event_type == "turn_failed"
    assert latest_audit.request_payload["error_code"] == "OH_UPSTREAM_TIMEOUT"


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
