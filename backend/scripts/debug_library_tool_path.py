#!/usr/bin/env python3
"""Debug the OpenHarness library-mode tool path without going through middlend SSE."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
OPENHARNESS_SRC = REPO_ROOT / "OpenHarness" / "src"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(OPENHARNESS_SRC) not in sys.path:
    sys.path.insert(0, str(OPENHARNESS_SRC))

load_dotenv(BACKEND_ROOT / ".env", override=False)

from app.adapters.openharness_client import _apply_tool_policy  # noqa: E402
from app.core.config import settings  # noqa: E402
from openharness.api.openai_client import OpenAICompatibleClient  # noqa: E402
from openharness.engine import stream_events as events_mod  # noqa: E402
from openharness.ui import runtime as runtime_mod  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "prompt",
        nargs="?",
        default="请帮我检索《劳动合同法》第47条和第87条，并说明违法解除劳动合同赔偿金的法律依据。",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    api_client = None
    if settings.oh_lib_api_key and settings.oh_lib_base_url:
        api_client = OpenAICompatibleClient(
            api_key=settings.oh_lib_api_key,
            base_url=settings.oh_lib_base_url,
        )

    bundle = await runtime_mod.build_runtime(
        model=settings.oh_lib_model or None,
        api_format=settings.oh_lib_api_format or None,
        base_url=settings.oh_lib_base_url or None,
        api_key=settings.oh_lib_api_key or None,
        api_client=api_client,
        cwd=settings.oh_lib_cwd or None,
        max_turns=settings.oh_lib_max_turns,
        permission_mode="full_auto",
        permission_prompt=None,
        ask_user_prompt=None,
        extra_skill_dirs=(BACKEND_ROOT / "agent-skills",),
    )
    # Force FULL_AUTO so MCP tools are not blocked by permission checker
    from openharness.permissions.modes import PermissionMode
    from openharness.config.settings import PermissionSettings
    from openharness.permissions import PermissionChecker
    bundle.engine.set_permission_checker(
        PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))
    )
    # Register local labor tools
    try:
        from app.tools import ALL_LOCAL_TOOLS
        for tool in ALL_LOCAL_TOOLS:
            bundle.tool_registry.register(tool)
        print(f"local_tools_registered={len(ALL_LOCAL_TOOLS)}: {', '.join(t.name for t in ALL_LOCAL_TOOLS)}")
    except Exception as e:
        print(f"local_tools_registration_failed: {e}")
    _apply_tool_policy(bundle, settings.oh_lib_tool_policy)

    print(f"api_client={type(bundle.api_client).__name__}")
    print(f"model={bundle.engine.model}")
    print(f"tool_policy={settings.oh_lib_tool_policy}")
    print("mcp_statuses:")
    for status in bundle.mcp_manager.list_statuses():
        print(f"  - {status.name}: {status.state} ({status.transport})")
        if status.tools:
            print("    tools:")
            for tool in status.tools:
                print(f"      * {tool.name}")

    tools = bundle.tool_registry.list_tools()
    print(f"tool_registry_count={len(tools)}")
    for tool in tools:
        print(f"  - {tool.name}")

    print("\nstream events:")
    try:
        async for event in bundle.engine.submit_message(args.prompt):
            if isinstance(event, events_mod.AssistantTextDelta):
                print(f"[text] {event.text!r}")
            elif isinstance(event, events_mod.ToolExecutionStarted):
                print(f"[tool_start] {event.tool_name} input={event.tool_input}")
            elif isinstance(event, events_mod.ToolExecutionCompleted):
                output = event.output.strip().replace("\n", " ")
                print(f"[tool_done] {event.tool_name} error={event.is_error} output={output[:400]}")
            elif isinstance(event, events_mod.AssistantTurnComplete):
                print(f"[final] text={event.message.text[:400]!r} tool_uses={len(event.message.tool_uses)}")
            elif isinstance(event, events_mod.ErrorEvent):
                print(f"[error] recoverable={event.recoverable} message={event.message}")
            else:
                print(f"[event] {event}")
    finally:
        await runtime_mod.close_runtime(bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
