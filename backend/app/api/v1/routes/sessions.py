from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.core.auth import Owner, resolve_owner
from app.models.schemas import EndSessionResponse, MessageResponse
from app.services.session_service import end_session, list_messages

router = APIRouter(tags=["sessions"])


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages_endpoint(session_id: str, owner: Owner = Depends(resolve_owner)):
    records = await list_messages(owner, session_id)
    return [MessageResponse(id=m.id, role=m.role, content=m.content, created_at=m.created_at) for m in records]


@router.patch("/sessions/{session_id}/end", response_model=EndSessionResponse)
async def end_session_endpoint(session_id: str, owner: Owner = Depends(resolve_owner)):
    session = await end_session(owner, session_id)
    return EndSessionResponse(
        id=session.id,
        status=session.status,
        ended_at=datetime.now(timezone.utc).isoformat(),
    )
