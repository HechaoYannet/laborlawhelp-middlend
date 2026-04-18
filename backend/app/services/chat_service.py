from datetime import datetime, timezone
from uuid import uuid4

from app.adapters.openharness_client import openharness_client
from app.core.auth import Owner
from app.core.errors import AppError
from app.core.sse import sse_event
from app.core.store import MessageRecord, store
from app.models.schemas import ChatRequest
from app.services.session_service import get_session


async def stream_chat(owner: Owner, session_id: str, request: ChatRequest):
    session = get_session(owner, session_id)
    if session.status != "active":
        raise AppError(410, "ANONYMOUS_SESSION_EXPIRED", "游客会话已过期或结束")

    lock = store.get_lock(session_id)
    if not lock.acquire(blocking=False):
        raise AppError(409, "SESSION_LOCKED", "同一会话有并发消息冲突", retryable=True)

    try:
        user_msg = MessageRecord(
            id=str(uuid4()),
            session_id=session_id,
            role="user",
            content=request.message,
        )
        store.messages.append(user_msg)

        assistant_id = str(uuid4())
        yield sse_event("message_start", {"message_id": assistant_id})

        full_text = ""
        seq = 0
        async for chunk in openharness_client.stream_run(request.message):
            if chunk.type == "text" and chunk.content:
                seq += 1
                full_text += chunk.content
                yield sse_event("content_delta", {"delta": chunk.content, "seq": seq})
            elif chunk.type == "tool_call":
                yield sse_event("tool_call", {"tool_name": chunk.tool_name, "args": chunk.args or {}})
            elif chunk.type == "tool_result":
                yield sse_event(
                    "tool_result",
                    {
                        "tool_name": chunk.tool_name,
                        "result_summary": (chunk.metadata or {}).get("status", "ok"),
                    },
                )
            elif chunk.type == "final":
                assistant_msg = MessageRecord(
                    id=assistant_id,
                    session_id=session_id,
                    role="assistant",
                    content=full_text,
                )
                store.messages.append(assistant_msg)
                session.message_count += 2
                session.last_active_at = datetime.now(timezone.utc).isoformat()
                yield sse_event(
                    "final",
                    {
                        "message_id": assistant_id,
                        "summary": (chunk.metadata or {}).get("summary", ""),
                        "references": (chunk.metadata or {}).get("references", []),
                        "rule_version": (chunk.metadata or {}).get("rule_version", "v2.2"),
                    },
                )
                break

        yield sse_event("message_end", {"message_id": assistant_id})
    except AppError:
        raise
    except Exception as exc:
        yield sse_event(
            "error",
            {
                "code": 500,
                "message": "服务暂时不可用，您可稍后重试。",
                "retryable": True,
                "detail": str(exc),
            },
        )
    finally:
        lock.release()
