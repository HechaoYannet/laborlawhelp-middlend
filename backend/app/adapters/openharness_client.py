from dataclasses import dataclass
from typing import AsyncGenerator


@dataclass
class OHChunk:
    type: str
    content: str | None = None
    tool_name: str | None = None
    args: dict | None = None
    metadata: dict | None = None


class OpenHarnessClient:
    async def stream_run(self, prompt: str) -> AsyncGenerator[OHChunk, None]:
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


openharness_client = OpenHarnessClient()
