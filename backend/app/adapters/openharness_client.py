from dataclasses import dataclass
import json
from typing import AsyncGenerator

import httpx

from app.core.config import settings
from app.core.errors import AppError


@dataclass
class OHChunk:
    type: str
    content: str | None = None
    tool_name: str | None = None
    args: dict | None = None
    metadata: dict | None = None


class OpenHarnessClient:
    async def _mock_stream_run(self, prompt: str) -> AsyncGenerator[OHChunk, None]:
        yield OHChunk(type="tool_call", tool_name="intent_router", args={"topic": "labor_dispute"})
        yield OHChunk(type="tool_result", tool_name="intent_router", metadata={"status": "ok"})
        parts = [
            "根据你提供的信息，先不要签署任何自愿离职文件。",
            "建议立即固定证据，包括劳动合同、工资记录和辞退沟通截图。",
            "可以先按未依法解除劳动合同方向准备仲裁材料。",
        ]
        for part in parts:
            yield OHChunk(type="text", content=part)
        yield OHChunk(
            type="final",
            metadata={
                "summary": "已给出初步维权路径和证据清单",
                "references": [],
                "rule_version": "v2.2",
            },
        )

    async def _remote_stream_run(
        self,
        prompt: str,
        session_id: str | None,
        user_context: dict,
    ) -> AsyncGenerator[OHChunk, None]:
        url = f"{settings.oh_base_url.rstrip('/')}{settings.oh_stream_path}"
        payload = {
            "prompt": prompt,
            "session_id": session_id,
            "workflow": settings.oh_default_workflow,
            "user_context": user_context,
            "output_format": "stream",
        }
        headers = {
            "Authorization": f"Bearer {settings.oh_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        raise AppError(500, "OH_SERVICE_ERROR", "OpenHarness执行异常", retryable=True)

                    event_name = ""
                    async for raw_line in response.aiter_lines():
                        line = raw_line.strip()
                        if not line:
                            continue
                        if line.startswith("event:"):
                            event_name = line.removeprefix("event:").strip()
                            continue
                        if not line.startswith("data:"):
                            continue

                        data_text = line.removeprefix("data:").strip()
                        try:
                            data = json.loads(data_text)
                        except json.JSONDecodeError:
                            continue

                        if event_name == "content_delta":
                            yield OHChunk(type="text", content=str(data.get("delta", "")))
                        elif event_name == "tool_call":
                            yield OHChunk(type="tool_call", tool_name=data.get("tool_name"), args=data.get("args", {}))
                        elif event_name == "tool_result":
                            yield OHChunk(
                                type="tool_result",
                                tool_name=data.get("tool_name"),
                                metadata={"status": data.get("result_summary", "ok")},
                            )
                        elif event_name == "final":
                            yield OHChunk(type="final", metadata=data)
                            break
        except AppError:
            raise
        except Exception as exc:
            raise AppError(500, "OH_SERVICE_ERROR", "OpenHarness执行异常", retryable=True) from exc

    async def stream_run(
        self,
        prompt: str,
        session_id: str | None,
        user_context: dict,
    ) -> AsyncGenerator[OHChunk, None]:
        if settings.oh_use_mock:
            async for chunk in self._mock_stream_run(prompt):
                yield chunk
            return

        async for chunk in self._remote_stream_run(prompt, session_id, user_context):
            yield chunk


openharness_client = OpenHarnessClient()
