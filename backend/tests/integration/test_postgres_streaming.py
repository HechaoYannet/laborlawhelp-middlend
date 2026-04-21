import asyncio
from collections.abc import Generator
import json
import os
import threading
import time
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.adapters.openharness import OHChunk
from app.core import rate_limit
from app.core.config import settings
from app.core.errors import AppError
from app.main import app
from app.modules.storage import InMemoryStore, PostgresRedisStore, set_store


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


def _create_case_and_session(client: TestClient, token: str) -> tuple[str, str]:
    headers = {"X-Anonymous-Token": token}
    case_resp = client.post("/api/v1/cases", json={"title": "it", "region_code": "xian"}, headers=headers)
    assert case_resp.status_code == 201
    case_id = case_resp.json()["id"]

    session_resp = client.post(f"/api/v1/cases/{case_id}/sessions", headers=headers)
    assert session_resp.status_code == 201
    session_data = session_resp.json()
    assert session_data["openharness_session_id"]
    UUID(session_data["openharness_session_id"])
    return case_id, session_data["id"]


@pytest.fixture()
def postgres_store(monkeypatch: pytest.MonkeyPatch) -> Generator[PostgresRedisStore, None, None]:
    _ = monkeypatch
    database_url = os.getenv("INTEGRATION_DATABASE_URL")
    redis_url = os.getenv("INTEGRATION_REDIS_URL")
    if not database_url or not redis_url:
        pytest.skip("需要设置 INTEGRATION_DATABASE_URL 与 INTEGRATION_REDIS_URL")

    old_auth_mode = settings.auth_mode
    old_storage_backend = settings.storage_backend
    old_rate = settings.rate_limit_per_minute
    old_oh_mock = settings.oh_use_mock
    old_db_url = settings.database_url
    old_redis_url = settings.redis_url

    settings.auth_mode = "anonymous"
    settings.storage_backend = "postgres"
    settings.rate_limit_per_minute = 50
    settings.oh_use_mock = True
    settings.database_url = database_url
    settings.redis_url = redis_url

    test_store = PostgresRedisStore()

    async def reset_runtime_state() -> None:
        engine = await test_store._engine_ref()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    TRUNCATE TABLE
                        audit_logs,
                        messages,
                        sessions,
                        cases
                    RESTART IDENTITY CASCADE
                    """
                )
            )
        redis = await test_store._redis_ref()
        await redis.flushdb()

    asyncio.run(reset_runtime_state())
    rate_limit._RATE_COUNTER.clear()
    set_store(test_store)

    yield test_store

    async def shutdown() -> None:
        if test_store._redis is not None:
            await test_store._redis.aclose()
        if test_store._engine is not None:
            await test_store._engine.dispose()

    asyncio.run(shutdown())
    settings.auth_mode = old_auth_mode
    settings.storage_backend = old_storage_backend
    settings.rate_limit_per_minute = old_rate
    settings.oh_use_mock = old_oh_mock
    settings.database_url = old_db_url
    settings.redis_url = old_redis_url
    set_store(InMemoryStore())


def test_postgres_stream_success_path_and_trace_consistency(postgres_store: PostgresRedisStore) -> None:
    client = TestClient(app)
    headers = {"X-Anonymous-Token": "anon-pg-success"}
    _, session_id = _create_case_and_session(client, "anon-pg-success")

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat/stream",
        json={"message": "请给我建议", "client_seq": 1, "attachments": []},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        payload = "".join(response.iter_text())

    events = _parse_sse_events(payload)
    event_names = [event for event, _ in events]
    assert event_names[0] == "message_start"
    assert event_names[-2] == "final"
    assert event_names[-1] == "message_end"

    final = next(data for event, data in events if event == "final")
    trace_id = final["trace_id"]
    assert trace_id

    messages = asyncio.run(postgres_store.list_messages(session_id))
    assistant = [m for m in messages if m.role == "assistant"][-1]
    assert assistant.metadata is not None
    assert assistant.metadata["status"] == "succeeded"
    assert assistant.metadata["trace_id"] == trace_id

    audits = asyncio.run(postgres_store.list_audit_logs(session_id))
    assert audits
    latest_audit = audits[-1]
    assert latest_audit.trace_id == trace_id
    assert latest_audit.event_type == "turn_completed"
    assert latest_audit.request_payload["trace_id"] == trace_id


def test_postgres_session_locked_conflict(postgres_store: PostgresRedisStore, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = postgres_store
    headers = {"X-Anonymous-Token": "anon-pg-lock"}

    with TestClient(app) as setup_client:
        _, session_id = _create_case_and_session(setup_client, "anon-pg-lock")

    async def slow_stream_run(**kwargs):
        trace_id = kwargs["trace_id"]
        yield OHChunk(type="text", content="正在处理")
        await asyncio.sleep(1.0)
        yield OHChunk(
            type="final",
            metadata={
                "summary": "完成",
                "references": [],
                "rule_version": "v2.2",
                "finish_reason": "stop",
                "trace_id": trace_id,
                "retry_count": 0,
            },
        )

    monkeypatch.setattr("app.modules.chat.service.openharness_client.stream_run", slow_stream_run)

    first_response: dict[str, str | int] = {}

    def run_first_request() -> None:
        with TestClient(app) as client:
            with client.stream(
                "POST",
                f"/api/v1/sessions/{session_id}/chat/stream",
                json={"message": "第一条", "client_seq": 1, "attachments": []},
                headers=headers,
            ) as response:
                first_response["status"] = response.status_code
                first_response["payload"] = "".join(response.iter_text())

    worker = threading.Thread(target=run_first_request)
    worker.start()
    time.sleep(0.2)

    with TestClient(app) as second_client:
        second = second_client.post(
            f"/api/v1/sessions/{session_id}/chat/stream",
            json={"message": "第二条", "client_seq": 2, "attachments": []},
            headers=headers,
        )

    worker.join(timeout=5)
    assert not worker.is_alive()

    assert second.status_code == 409
    assert second.json()["code"] == "SESSION_LOCKED"
    assert second.json()["retryable"] is True
    assert first_response["status"] == 200


def test_postgres_error_path_message_end_and_failed_metadata(
    postgres_store: PostgresRedisStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    headers = {"X-Anonymous-Token": "anon-pg-error"}
    _, session_id = _create_case_and_session(client, "anon-pg-error")

    async def broken_stream_run(**_: dict):
        yield OHChunk(type="text", content="先返回一点文本")
        raise AppError(504, "OH_UPSTREAM_TIMEOUT", "OpenHarness 请求超时", retryable=True)

    monkeypatch.setattr("app.modules.chat.service.openharness_client.stream_run", broken_stream_run)

    with client.stream(
        "POST",
        f"/api/v1/sessions/{session_id}/chat/stream",
        json={"message": "模拟异常", "client_seq": 1, "attachments": []},
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
    assert error["code"] == "OH_UPSTREAM_TIMEOUT"
    trace_id = error["trace_id"]

    messages = asyncio.run(postgres_store.list_messages(session_id))
    assistant = [m for m in messages if m.role == "assistant"][-1]
    assert assistant.content == ""
    assert assistant.metadata is not None
    assert assistant.metadata["status"] == "failed"
    assert assistant.metadata["trace_id"] == trace_id
    assert assistant.metadata["error_code"] == "OH_UPSTREAM_TIMEOUT"

    audits = asyncio.run(postgres_store.list_audit_logs(session_id))
    assert audits
    latest_audit = audits[-1]
    assert latest_audit.trace_id == trace_id
    assert latest_audit.event_type == "turn_failed"
    assert latest_audit.request_payload["error_code"] == "OH_UPSTREAM_TIMEOUT"
