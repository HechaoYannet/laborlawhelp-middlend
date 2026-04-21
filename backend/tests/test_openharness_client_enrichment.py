import asyncio
from collections.abc import Generator
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.adapters.openharness_client import OpenHarnessClient, _apply_tool_policy
from app.core.config import settings
from openharness.engine.messages import ConversationMessage, TextBlock
from openharness.tools.base import ToolRegistry


@pytest.fixture(autouse=True)
def reset_openharness_mode_settings() -> Generator[None, None, None]:
    old_mode = settings.oh_mode
    old_mock = settings.oh_use_mock
    yield
    settings.oh_mode = old_mode
    settings.oh_use_mock = old_mock


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
