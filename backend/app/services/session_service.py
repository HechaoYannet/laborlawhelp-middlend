from datetime import datetime, timezone

from app.core.auth import Owner
from app.core.errors import AppError
from app.core.store import MessageRecord, SessionRecord, store
from app.services.case_service import get_case


def create_session(owner: Owner, case_id: str) -> SessionRecord:
    get_case(owner, case_id)
    session_id = store.new_id()
    session = SessionRecord(
        id=session_id,
        case_id=case_id,
        owner_type=owner.owner_type,
        owner_id=owner.owner_id,
    )
    store.sessions[session_id] = session
    return session


def list_sessions(owner: Owner, case_id: str) -> list[SessionRecord]:
    get_case(owner, case_id)
    return [
        s
        for s in store.sessions.values()
        if s.case_id == case_id and s.owner_id == owner.owner_id and s.owner_type == owner.owner_type
    ]


def get_session(owner: Owner, session_id: str) -> SessionRecord:
    session = store.sessions.get(session_id)
    if not session:
        raise AppError(404, "SESSION_NOT_FOUND", "Session not found")
    if session.owner_id != owner.owner_id or session.owner_type != owner.owner_type:
        raise AppError(403, "FORBIDDEN", "无权访问该会话")
    return session


def list_messages(owner: Owner, session_id: str) -> list[MessageRecord]:
    get_session(owner, session_id)
    return [m for m in store.messages if m.session_id == session_id]


def end_session(owner: Owner, session_id: str) -> SessionRecord:
    session = get_session(owner, session_id)
    session.status = "ended"
    session.last_active_at = datetime.now(timezone.utc).isoformat()
    return session
