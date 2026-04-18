from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.auth import Owner, resolve_owner
from app.core.rate_limit import check_rate_limit
from app.models.schemas import ChatRequest
from app.services.chat_service import stream_chat

router = APIRouter(tags=["chat"])


@router.post("/sessions/{session_id}/chat")
async def chat_stream_endpoint(
    session_id: str,
    payload: ChatRequest,
    owner: Owner = Depends(resolve_owner),
):
    await check_rate_limit(owner.owner_id)
    event_generator = stream_chat(owner, session_id, payload)
    return StreamingResponse(event_generator, media_type="text/event-stream")
