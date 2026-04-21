from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.errors import AppError
from app.core.rate_limit import check_rate_limit
from app.modules.auth import Owner, resolve_owner
from app.modules.case_session.service import get_session
from app.modules.chat.schemas import ChatRequest
from app.modules.chat.service import stream_chat

router = APIRouter(tags=["chat"])


async def _chat_stream(
    session_id: str,
    payload: ChatRequest,
    owner: Owner,
):
    session = await get_session(owner, session_id)
    if session.status != "active":
        raise AppError(410, "ANONYMOUS_SESSION_EXPIRED", "游客会话已过期或结束")

    await check_rate_limit(owner.owner_id)
    event_generator = stream_chat(owner, session_id, payload)
    return StreamingResponse(event_generator, media_type="text/event-stream")


@router.post("/sessions/{session_id}/chat")
async def chat_stream_compat_endpoint(
    session_id: str,
    payload: ChatRequest,
    owner: Owner = Depends(resolve_owner),
):
    return await _chat_stream(session_id, payload, owner)


@router.post("/sessions/{session_id}/chat/stream")
async def chat_stream_endpoint(
    session_id: str,
    payload: ChatRequest,
    owner: Owner = Depends(resolve_owner),
):
    return await _chat_stream(session_id, payload, owner)
