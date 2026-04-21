from app.adapters.openharness import OHChunk
from app.core.errors import AppError
from app.core.sse import sse_event


def message_start_event(message_id: str, trace_id: str) -> str:
    return sse_event("message_start", {"message_id": message_id, "trace_id": trace_id})


def message_end_event(message_id: str, trace_id: str) -> str:
    return sse_event("message_end", {"message_id": message_id, "trace_id": trace_id})


def content_delta_event(delta: str, seq: int, trace_id: str) -> str:
    return sse_event("content_delta", {"delta": delta, "seq": seq, "trace_id": trace_id})


def tool_call_event(chunk: OHChunk, trace_id: str) -> str:
    return sse_event(
        "tool_call",
        {
            "tool_name": chunk.tool_name,
            "args": chunk.args or {},
            "trace_id": trace_id,
        },
    )


def tool_result_event(chunk: OHChunk, trace_id: str) -> str:
    tool_metadata = chunk.metadata or {}
    return sse_event(
        "tool_result",
        {
            "tool_name": chunk.tool_name,
            "result_summary": tool_metadata.get("result_summary") or tool_metadata.get("status", "ok"),
            "references": tool_metadata.get("references", []),
            "card_type": tool_metadata.get("card_type"),
            "card_title": tool_metadata.get("card_title"),
            "card_payload": tool_metadata.get("card_payload"),
            "card_actions": tool_metadata.get("card_actions", []),
            "trace_id": trace_id,
        },
    )


def final_event(message_id: str, metadata: dict, finish_reason: str, trace_id: str) -> str:
    return sse_event(
        "final",
        {
            "message_id": message_id,
            "summary": metadata.get("summary", ""),
            "references": metadata.get("references", []),
            "rule_version": metadata.get("rule_version", "v2.2"),
            "finish_reason": finish_reason,
            "trace_id": trace_id,
        },
    )


def error_event(exc: AppError, trace_id: str) -> str:
    return sse_event(
        "error",
        {
            "code": exc.code,
            "message": exc.message,
            "retryable": exc.retryable,
            "trace_id": trace_id,
        },
    )
