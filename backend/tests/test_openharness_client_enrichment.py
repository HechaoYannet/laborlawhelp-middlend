import asyncio
from collections.abc import Generator
from dataclasses import dataclass
from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError

from app.adapters.openharness import OpenHarnessClient, _apply_tool_policy
from app.adapters.openharness.client import (
    _error_event_to_app_error,
    _is_retryable_openai_stream_error,
    _normalize_assistant_reasoning_content,
)
from app.core.config import settings
from app.core.errors import AppError
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.mcp.types import McpConnectionStatus, McpToolInfo
from openharness.tools.base import ToolRegistry


@pytest.fixture(autouse=True)
def reset_openharness_mode_settings() -> Generator[None, None, None]:
    old_mode = settings.oh_mode
    old_mock = settings.oh_use_mock
    old_keep_reasoning = settings.oh_lib_keep_empty_reasoning_content
    old_tool_policy = settings.oh_lib_tool_policy
    yield
    settings.oh_mode = old_mode
    settings.oh_use_mock = old_mock
    settings.oh_lib_keep_empty_reasoning_content = old_keep_reasoning
    settings.oh_lib_tool_policy = old_tool_policy


def _collect(client: OpenHarnessClient, **kwargs):
    async def run():
        items = []
        async for chunk in client.stream_run(
            prompt="张女士被口头辞退，公司没有书面通知。",
            session_id="oh-session-1",
            user_context={"owner_id": "anon-1", "owner_type": "anonymous"},
            trace_id="trace-test-1",
            **kwargs,
        ):
            items.append(chunk)
        return items

    return asyncio.run(run())


def test_stream_run_prefers_mock_when_oh_use_mock_true_even_if_mode_is_library() -> None:
    settings.oh_mode = "library"
    settings.oh_use_mock = True

    chunks = _collect(OpenHarnessClient())

    assert [chunk.type for chunk in chunks] == ["tool_call", "tool_result", "text", "text", "text", "final"]
    assert chunks[-1].metadata is not None
    assert chunks[-1].metadata["summary"] == "已给出初步维权路径和证据清单"


def test_library_mode_enriches_final_with_pkulaw_references(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.oh_mode = "library"
    settings.oh_use_mock = False

    @dataclass(frozen=True)
    class AssistantTextDelta:
        text: str

    @dataclass(frozen=True)
    class AssistantTurnComplete:
        message: ConversationMessage
        usage: object | None = None

    @dataclass(frozen=True)
    class ToolExecutionStarted:
        tool_name: str
        tool_input: dict

    @dataclass(frozen=True)
    class ToolExecutionCompleted:
        tool_name: str
        output: str
        is_error: bool = False

    @dataclass(frozen=True)
    class ErrorEvent:
        message: str
        recoverable: bool = True

    class FakeEngine:
        def __init__(self) -> None:
            self.last_prompt = ""

        async def submit_message(self, prompt: str):
            self.last_prompt = prompt
            yield AssistantTextDelta("初步判断：构成违法解除。")
            yield ToolExecutionStarted(
                tool_name="mcp__pkulaw__fatiao_keyword",
                tool_input={"query": "劳动合同法 第87条"},
            )
            yield ToolExecutionCompleted(
                tool_name="mcp__pkulaw__fatiao_keyword",
                output=(
                    '{"citations":[{"title":"劳动合同法第87条",'
                    '"source_url":"https://pkulaw.example.com/doc/87",'
                    '"excerpt":"用人单位违法解除劳动合同的，应当依照本法第47条规定的经济补偿标准的二倍向劳动者支付赔偿金。"}]}'
                ),
            )
            yield AssistantTurnComplete(
                ConversationMessage(
                    role="assistant",
                    content=[TextBlock(text="初步判断：构成违法解除。建议尽快准备仲裁材料。")],
                )
            )

    fake_engine = FakeEngine()
    fake_registry = ToolRegistry()
    fake_registry.register(SimpleNamespace(name="skill"))
    fake_registry.register(SimpleNamespace(name="mcp__pkulaw__fatiao_keyword"))
    fake_bundle = SimpleNamespace(
        engine=fake_engine,
        tool_registry=fake_registry,
        mcp_manager=SimpleNamespace(
            list_statuses=lambda: [SimpleNamespace(name="pkulaw", state="connected")]
        ),
    )

    async def fake_get_or_create_bundle(session_id: str | None):
        _ = session_id
        return fake_bundle

    fake_events_module = SimpleNamespace(
        AssistantTextDelta=AssistantTextDelta,
        AssistantTurnComplete=AssistantTurnComplete,
        ToolExecutionStarted=ToolExecutionStarted,
        ToolExecutionCompleted=ToolExecutionCompleted,
        ErrorEvent=ErrorEvent,
    )

    client = OpenHarnessClient()
    monkeypatch.setattr(client, "_get_or_create_bundle", fake_get_or_create_bundle)
    monkeypatch.setattr("app.adapters.openharness.client._load_oh_modules", lambda: (object(), fake_events_module))

    chunks = _collect(
        client,
        locale="zh-CN",
        policy_version="shaanxi.illegal_termination.v1",
        client_capabilities=["citations", "tool-status"],
    )

    assert fake_engine.last_prompt
    assert 'skill(name="labor-pkulaw-retrieval-flow")' in fake_engine.last_prompt
    assert '禁止向用户暴露内部执行过程' in fake_engine.last_prompt
    assert '不要输出“我将按照劳动争议智能分诊工作流为您分析”' in fake_engine.last_prompt
    assert "mcp__pkulaw__" in fake_engine.last_prompt
    assert "shaanxi.illegal_termination.v1" in fake_engine.last_prompt

    tool_result = next(chunk for chunk in chunks if chunk.type == "tool_result")
    assert tool_result.metadata is not None
    assert tool_result.metadata["result_summary"] == "retrieved 1 legal reference(s)"
    assert tool_result.metadata["references"][0]["title"] == "劳动合同法第87条"

    final = next(chunk for chunk in chunks if chunk.type == "final")
    assert final.metadata is not None
    assert final.metadata["rule_version"] == "shaanxi.illegal_termination.v1"
    assert final.metadata["references"][0]["url"] == "https://pkulaw.example.com/doc/87"
    assert "违法解除" in final.metadata["summary"]


def test_legal_minimal_tool_policy_keeps_skill_and_pkulaw_tools() -> None:
    registry = ToolRegistry()
    registry.register(SimpleNamespace(name="skill"))
    registry.register(SimpleNamespace(name="mcp__pkulaw__fatiao_keyword"))
    registry.register(SimpleNamespace(name="read_mcp_resource"))
    registry.register(SimpleNamespace(name="labor_fact_extract"))
    registry.register(SimpleNamespace(name="labor_lawyer_recommend"))
    registry.register(SimpleNamespace(name="bash"))

    fake_bundle = SimpleNamespace(tool_registry=registry, engine=SimpleNamespace())

    _apply_tool_policy(fake_bundle, "legal_minimal")

    kept = [tool.name for tool in fake_bundle.tool_registry.list_tools()]
    assert "skill" in kept
    assert "mcp__pkulaw__fatiao_keyword" in kept
    assert "read_mcp_resource" in kept
    assert "labor_fact_extract" in kept
    assert "labor_lawyer_recommend" in kept
    assert "bash" not in kept


def test_library_mode_builds_card_metadata_for_local_compensation_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.oh_mode = "library"
    settings.oh_use_mock = False

    @dataclass(frozen=True)
    class ToolExecutionCompleted:
        tool_name: str
        output: str
        is_error: bool = False

    @dataclass(frozen=True)
    class AssistantTurnComplete:
        message: ConversationMessage
        usage: object | None = None

    class FakeEngine:
        async def submit_message(self, prompt: str):
            _ = prompt
            yield ToolExecutionCompleted(
                tool_name="labor_compensation_calc",
                output='{"calculations":[{"item":"违法解除赔偿金（2N）","formula":"12000 × 2 = 24000","amount":24000}],"total_amount":24000,"input_summary":{"work_years":2}}',
            )
            yield AssistantTurnComplete(
                ConversationMessage(
                    role="assistant",
                    content=[TextBlock(text="已完成测算")],
                )
            )

    fake_bundle = SimpleNamespace(
        engine=FakeEngine(),
        tool_registry=ToolRegistry(),
        mcp_manager=SimpleNamespace(list_statuses=lambda: []),
    )

    async def fake_get_or_create_bundle(session_id: str | None):
        _ = session_id
        return fake_bundle

    fake_events_module = SimpleNamespace(
        ToolExecutionCompleted=ToolExecutionCompleted,
        AssistantTurnComplete=AssistantTurnComplete,
        AssistantTextDelta=type("AssistantTextDelta", (), {}),
        ToolExecutionStarted=type("ToolExecutionStarted", (), {}),
        ErrorEvent=type("ErrorEvent", (), {}),
    )

    client = OpenHarnessClient()
    monkeypatch.setattr(client, "_get_or_create_bundle", fake_get_or_create_bundle)
    monkeypatch.setattr("app.adapters.openharness.client._load_oh_modules", lambda: (object(), fake_events_module))

    chunks = _collect(client)
    tool_result = next(chunk for chunk in chunks if chunk.type == "tool_result")
    assert tool_result.metadata is not None
    assert tool_result.metadata["card_type"] == "compensation"
    assert tool_result.metadata["card_title"] == "测算赔偿项目"
    assert isinstance(tool_result.metadata["card_payload"], dict)
    assert tool_result.metadata["card_actions"][0]["action"] == "generate_document"


def test_normalize_assistant_reasoning_content_drops_empty_value_by_default() -> None:
    settings.oh_lib_keep_empty_reasoning_content = False

    normalized = _normalize_assistant_reasoning_content(
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "labor_fact_extract", "arguments": "{}"},
                }
            ],
        }
    )

    assert "reasoning_content" not in normalized
    assert normalized["tool_calls"][0]["function"]["name"] == "labor_fact_extract"


def test_normalize_assistant_reasoning_content_keeps_empty_value_when_enabled() -> None:
    settings.oh_lib_keep_empty_reasoning_content = True

    normalized = _normalize_assistant_reasoning_content(
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "labor_fact_extract", "arguments": "{}"},
                }
            ],
        }
    )

    assert normalized["reasoning_content"] == ""


def test_library_mode_reconnects_failed_mcp_and_registers_pkulaw_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.oh_mode = "library"
    settings.oh_use_mock = False
    settings.oh_lib_tool_policy = "legal_minimal"

    @dataclass(frozen=True)
    class AssistantTurnComplete:
        message: ConversationMessage
        usage: object | None = None

    class FakeEngine:
        def __init__(self) -> None:
            self.last_prompt = ""

        async def submit_message(self, prompt: str):
            self.last_prompt = prompt
            yield AssistantTurnComplete(
                ConversationMessage(
                    role="assistant",
                    content=[TextBlock(text="已恢复 PKULaw 连接并完成回答。")],
                )
            )

    class FakeMcpManager:
        def __init__(self) -> None:
            self._connected = False
            self.reconnect_calls = 0

        def list_statuses(self):
            if self._connected:
                return [
                    McpConnectionStatus(
                        name="pkulaw",
                        state="connected",
                        transport="stdio",
                        tools=[
                            McpToolInfo(
                                server_name="pkulaw",
                                name="search_article",
                                description="search",
                                input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
                            )
                        ],
                    )
                ]
            return [
                McpConnectionStatus(
                    name="pkulaw",
                    state="failed",
                    transport="stdio",
                    detail="boot failed",
                )
            ]

        def list_tools(self):
            statuses = self.list_statuses()
            tools = []
            for status in statuses:
                tools.extend(status.tools)
            return tools

        async def reconnect_all(self) -> None:
            self.reconnect_calls += 1
            self._connected = True

    fake_registry = ToolRegistry()
    fake_registry.register(SimpleNamespace(name="skill"))
    fake_registry.register(SimpleNamespace(name="list_mcp_resources"))
    fake_registry.register(SimpleNamespace(name="read_mcp_resource"))
    fake_registry.register(SimpleNamespace(name="labor_fact_extract"))

    fake_engine = FakeEngine()
    fake_bundle = SimpleNamespace(
        engine=fake_engine,
        tool_registry=fake_registry,
        mcp_manager=FakeMcpManager(),
    )

    async def fake_get_or_create_bundle(session_id: str | None):
        _ = session_id
        return fake_bundle

    fake_events_module = SimpleNamespace(
        AssistantTurnComplete=AssistantTurnComplete,
        AssistantTextDelta=type("AssistantTextDelta", (), {}),
        ToolExecutionStarted=type("ToolExecutionStarted", (), {}),
        ToolExecutionCompleted=type("ToolExecutionCompleted", (), {}),
        ErrorEvent=type("ErrorEvent", (), {}),
    )

    client = OpenHarnessClient()
    monkeypatch.setattr(client, "_get_or_create_bundle", fake_get_or_create_bundle)
    monkeypatch.setattr("app.adapters.openharness.client._load_oh_modules", lambda: (object(), fake_events_module))

    chunks = _collect(client)

    assert [chunk.type for chunk in chunks] == ["final"]
    assert fake_bundle.mcp_manager.reconnect_calls == 1
    tool_names = [tool.name for tool in fake_bundle.tool_registry.list_tools()]
    assert "mcp__pkulaw__search_article" in tool_names
    assert "当前未检测到 PKULaw MCP 工具" not in fake_engine.last_prompt


def test_is_retryable_openai_stream_error_accepts_sdk_connection_error() -> None:
    request = httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions")
    error = APIConnectionError(
        message="peer closed connection without sending complete message body (incomplete chunked read)",
        request=request,
    )

    assert _is_retryable_openai_stream_error(error, lambda exc: False) is True


def test_error_event_to_app_error_preserves_timeout_message() -> None:
    error = _error_event_to_app_error(
        "API error: Request timed out.",
        recoverable=True,
    )

    assert isinstance(error, AppError)
    assert error.code == "OH_UPSTREAM_TIMEOUT"
    assert error.retryable is True
    assert error.message == "API error: Request timed out."
