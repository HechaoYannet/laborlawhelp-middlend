from uuid import uuid4

from app.adapters.openharness_client import openharness_client
from app.core.auth import Owner
from app.core.errors import AppError
from app.core.sse import sse_event
from app.core.store import store
from app.models.schemas import ChatRequest
from app.services.session_service import get_session


async def stream_chat(owner: Owner, session_id: str, request: ChatRequest):
    session = await get_session(owner, session_id)

    async with store.acquire_session_lock(session_id):
        try:
            await store.save_message(session_id=session_id, role="user", content=request.message)

            assistant_id = str(uuid4())
            yield sse_event("message_start", {"message_id": assistant_id})

            full_text = ""
            async for chunk in openharness_client.stream_run(
                prompt=request.message,
                session_id=session.openharness_session_id,
                user_context={
                    "owner_type": owner.owner_type,
                    "owner_id": owner.owner_id,
                },
            ):
                if chunk.type == "text" and chunk.content:
                    seq = await store.next_stream_seq(session_id)
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
                    await store.save_message(
                        session_id=session_id,
                        role="assistant",
                        content=full_text,
                        message_id=assistant_id,
                    )
                    await store.update_session_activity(session_id, message_increment=2)
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
