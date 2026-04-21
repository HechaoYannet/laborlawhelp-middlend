from datetime import datetime, timezone

from app.modules.auth import Owner
from app.core.errors import AppError
from app.modules.storage import CaseRecord, MessageRecord, SessionRecord, get_store


async def create_case(owner: Owner, title: str, region_code: str) -> CaseRecord:
    return await get_store().create_case(owner.owner_type, owner.owner_id, title, region_code)


async def list_cases(owner: Owner) -> list[CaseRecord]:
    return await get_store().list_cases(owner.owner_type, owner.owner_id)


async def get_case(owner: Owner, case_id: str) -> CaseRecord:
    case_record = await get_store().get_case(case_id)
    if not case_record:
        raise AppError(404, "CASE_NOT_FOUND", "Case not found")
    if case_record.owner_id != owner.owner_id or case_record.owner_type != owner.owner_type:
        raise AppError(403, "FORBIDDEN", "无权访问该案件")
    return case_record


async def create_session(owner: Owner, case_id: str) -> SessionRecord:
    await get_case(owner, case_id)
    return await get_store().create_session(case_id, owner.owner_type, owner.owner_id)


async def list_sessions(owner: Owner, case_id: str) -> list[SessionRecord]:
    await get_case(owner, case_id)
    return await get_store().list_sessions(case_id, owner.owner_type, owner.owner_id)


async def get_session(owner: Owner, session_id: str) -> SessionRecord:
    session = await get_store().get_session(session_id)
    if not session:
        raise AppError(404, "SESSION_NOT_FOUND", "Session not found")
    if session.owner_id != owner.owner_id or session.owner_type != owner.owner_type:
        raise AppError(403, "FORBIDDEN", "无权访问该会话")
    return session


async def list_messages(owner: Owner, session_id: str) -> list[MessageRecord]:
    await get_session(owner, session_id)
    return await get_store().list_messages(session_id)


async def end_session(owner: Owner, session_id: str) -> SessionRecord:
    await get_session(owner, session_id)
    session = await get_store().end_session(session_id)
    if not session:
        raise AppError(404, "SESSION_NOT_FOUND", "Session not found")
    session.last_active_at = datetime.now(timezone.utc).isoformat()
    return session
