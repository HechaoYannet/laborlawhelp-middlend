from dataclasses import dataclass


@dataclass
class OHChunk:
    type: str
    content: str | None = None
    tool_name: str | None = None
    args: dict | None = None
    metadata: dict | None = None
