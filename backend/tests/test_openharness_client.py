import asyncio
from collections.abc import Generator

import httpx
import pytest

from app.adapters.openharness_client import OpenHarnessClient
from app.core.config import settings
from app.core.errors import AppError


class FakeResponse:
    def __init__(self, *, status_code: int, lines: list[str | Exception]):
        self.status_code = status_code
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            if isinstance(line, Exception):
                raise line
            yield line


class FakeAsyncClient:
    def __init__(self, responses: list[FakeResponse], call_counter: dict[str, int], **_: dict):
        self._responses = responses
        self._call_counter = call_counter

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def stream(self, method: str, url: str, json: dict, headers: dict):
        _ = (method, url, json, headers)
        self._call_counter["count"] += 1
        if not self._responses:
            raise AssertionError("no fake response left")
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def reset_openharness_settings() -> Generator[None, None, None]:
    old = {
        "oh_mode": settings.oh_mode,
        "oh_use_mock": settings.oh_use_mock,
        "oh_retry_max_attempts": settings.oh_retry_max_attempts,
        "oh_retry_backoff_seconds": settings.oh_retry_backoff_seconds,
        "oh_first_chunk_timeout_sec": settings.oh_first_chunk_timeout_sec,
        "oh_connect_timeout_sec": settings.oh_connect_timeout_sec,
        "oh_read_timeout_sec": settings.oh_read_timeout_sec,
        "oh_protocol_error_threshold": settings.oh_protocol_error_threshold,
    }
    settings.oh_mode = "remote"
    settings.oh_use_mock = False
    settings.oh_retry_max_attempts = 3
    settings.oh_retry_backoff_seconds = "0,0,0"
    settings.oh_first_chunk_timeout_sec = 3
    settings.oh_connect_timeout_sec = 1
    settings.oh_read_timeout_sec = 3
    settings.oh_protocol_error_threshold = 3
    yield
    settings.oh_mode = old["oh_mode"]
    settings.oh_use_mock = old["oh_use_mock"]
    settings.oh_retry_max_attempts = old["oh_retry_max_attempts"]
    settings.oh_retry_backoff_seconds = old["oh_retry_backoff_seconds"]
    settings.oh_first_chunk_timeout_sec = old["oh_first_chunk_timeout_sec"]
    settings.oh_connect_timeout_sec = old["oh_connect_timeout_sec"]
    settings.oh_read_timeout_sec = old["oh_read_timeout_sec"]
    settings.oh_protocol_error_threshold = old["oh_protocol_error_threshold"]


def _patch_client(monkeypatch: pytest.MonkeyPatch, responses: list[FakeResponse], call_counter: dict[str, int]) -> None:
    def factory(*args, **kwargs):
        _ = args
        return FakeAsyncClient(responses=responses, call_counter=call_counter, **kwargs)

    monkeypatch.setattr("app.adapters.openharness_client.httpx.AsyncClient", factory)


def _collect_chunks(client: OpenHarnessClient):
    async def run():
        items = []
        async for chunk in client.stream_run(
            prompt="hello",
            session_id="s1",
            user_context={"owner_id": "u1", "owner_type": "anonymous"},
            trace_id="trace-1",
            client_capabilities=[],
        ):
            items.append(chunk)
        return items

    return asyncio.run(run())


def test_remote_parser_skips_unknown_and_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        FakeResponse(
            status_code=200,
            lines=[
                "event: content_delta",
                'data: {"delta":"A"}',
                "event: unknown_event",
                'data: {"x":1}',
                "event: content_delta",
                "data: this-is-not-json",
                "event: final",
                'data: {"summary":"done"}',
            ],
        )
    ]
    calls = {"count": 0}
    _patch_client(monkeypatch, responses, calls)

    chunks = _collect_chunks(OpenHarnessClient())
    assert calls["count"] == 1
    assert [chunk.type for chunk in chunks] == ["text", "final"]
    assert chunks[-1].metadata is not None
    assert chunks[-1].metadata["trace_id"] == "trace-1"


def test_remote_parser_raises_protocol_error_after_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        FakeResponse(
            status_code=200,
            lines=[
                "event: unknown_event",
                'data: {"x":1}',
                "event: unknown_event",
                'data: {"x":2}',
                "event: unknown_event",
                'data: {"x":3}',
            ],
        )
    ]
    calls = {"count": 0}
    _patch_client(monkeypatch, responses, calls)

    with pytest.raises(AppError) as exc:
        _collect_chunks(OpenHarnessClient())
    assert calls["count"] == 1
    assert exc.value.code == "OH_PROTOCOL_ERROR"


def test_retries_before_first_business_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        FakeResponse(status_code=200, lines=[httpx.ReadTimeout("timeout", request=None)]),
        FakeResponse(
            status_code=200,
            lines=[
                "event: final",
                'data: {"summary":"ok"}',
            ],
        ),
    ]
    calls = {"count": 0}
    _patch_client(monkeypatch, responses, calls)

    chunks = _collect_chunks(OpenHarnessClient())
    assert calls["count"] == 2
    assert [chunk.type for chunk in chunks] == ["final"]
    assert chunks[0].metadata is not None
    assert chunks[0].metadata["retry_count"] == 1


def test_no_retry_after_business_chunk_started(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        FakeResponse(
            status_code=200,
            lines=[
                "event: content_delta",
                'data: {"delta":"hello"}',
                httpx.ReadTimeout("timeout", request=None),
            ],
        ),
        FakeResponse(
            status_code=200,
            lines=[
                "event: final",
                'data: {"summary":"should-not-reach"}',
            ],
        ),
    ]
    calls = {"count": 0}
    _patch_client(monkeypatch, responses, calls)

    async def run():
        collected = []
        caught = None
        client = OpenHarnessClient()
        try:
            async for chunk in client.stream_run(
                prompt="hello",
                session_id="s1",
                user_context={"owner_id": "u1", "owner_type": "anonymous"},
                trace_id="trace-1",
                client_capabilities=[],
            ):
                collected.append(chunk)
        except AppError as exc:
            caught = exc
        return collected, caught

    chunks, error = asyncio.run(run())
    assert calls["count"] == 1
    assert [chunk.type for chunk in chunks] == ["text"]
    assert error is not None
    assert error.code == "OH_UPSTREAM_TIMEOUT"
