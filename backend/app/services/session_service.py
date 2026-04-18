from datetime import datetime, timezone

from app.core.auth import Owner
from app.core.errors import AppError
from app.core.store import MessageRecord, SessionRecord, store
from app.services.case_service import get_case


async def create_session(owner: Owner, case_id: str) -> SessionRecord:
    await get_case(owner, case_id)
    return await store.create_session(case_id, owner.owner_type, owner.owner_id)


async def list_sessions(owner: Owner, case_id: str) -> list[SessionRecord]:
    await get_case(owner, case_id)
    return await store.list_sessions(case_id, owner.owner_type, owner.owner_id)


async def get_session(owner: Owner, session_id: str) -> SessionRecord:
    session = await store.get_session(session_id)
    if not session:
        raise AppError(404, "SESSION_NOT_FOUND", "Session not found")
    if session.owner_id != owner.owner_id or session.owner_type != owner.owner_type:
        raise AppError(403, "FORBIDDEN", "无权访问该会话")
    return session


async def list_messages(owner: Owner, session_id: str) -> list[MessageRecord]:
    await get_session(owner, session_id)
    return await store.list_messages(session_id)


async def end_session(owner: Owner, session_id: str) -> SessionRecord:
    await get_session(owner, session_id)
    session = await store.end_session(session_id)
    if not session:
        raise AppError(404, "SESSION_NOT_FOUND", "Session not found")
    session.last_active_at = datetime.now(timezone.utc).isoformat()
    return session
