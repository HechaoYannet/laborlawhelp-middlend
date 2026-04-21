import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from app.core.errors import AppError
from app.modules.storage.protocol import BaseStore
from app.modules.storage.records import AuditLogRecord, CaseRecord, MessageRecord, SessionRecord


class InMemoryStore(BaseStore):
    def __init__(self) -> None:
        self.cases: dict[str, CaseRecord] = {}
        self.sessions: dict[str, SessionRecord] = {}
        self.messages: list[MessageRecord] = []
        self.audit_logs: list[AuditLogRecord] = []
        self.session_locks: dict[str, asyncio.Lock] = {}
        self.stream_seq: dict[str, int] = {}

    def new_id(self) -> str:
        return str(uuid4())

    def get_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self.session_locks:
            self.session_locks[session_id] = asyncio.Lock()
        return self.session_locks[session_id]

    async def create_case(self, owner_type: str, owner_id: str, title: str, region_code: str) -> CaseRecord:
        case_id = self.new_id()
        record = CaseRecord(id=case_id, owner_type=owner_type, owner_id=owner_id, title=title, region_code=region_code)
        self.cases[case_id] = record
        return record

    async def list_cases(self, owner_type: str, owner_id: str) -> list[CaseRecord]:
        return [case for case in self.cases.values() if case.owner_type == owner_type and case.owner_id == owner_id]

    async def get_case(self, case_id: str) -> CaseRecord | None:
        return self.cases.get(case_id)

    async def create_session(self, case_id: str, owner_type: str, owner_id: str) -> SessionRecord:
        session_id = self.new_id()
        openharness_session_id = self.new_id()
        session = SessionRecord(
            id=session_id,
            case_id=case_id,
            owner_type=owner_type,
            owner_id=owner_id,
            openharness_session_id=openharness_session_id,
        )
        self.sessions[session_id] = session
        return session

    async def list_sessions(self, case_id: str, owner_type: str, owner_id: str) -> list[SessionRecord]:
        return [
            session
            for session in self.sessions.values()
            if session.case_id == case_id and session.owner_type == owner_type and session.owner_id == owner_id
        ]

    async def get_session(self, session_id: str) -> SessionRecord | None:
        return self.sessions.get(session_id)

    async def end_session(self, session_id: str) -> SessionRecord | None:
        session = self.sessions.get(session_id)
        if not session:
            return None
        session.status = "ended"
        session.last_active_at = datetime.now(timezone.utc).isoformat()
        return session

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_id: str | None = None,
        metadata: dict | None = None,
    ) -> MessageRecord:
        message = MessageRecord(
            id=message_id or self.new_id(),
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata,
        )
        self.messages.append(message)
        return message

    async def list_messages(self, session_id: str) -> list[MessageRecord]:
        return [message for message in self.messages if message.session_id == session_id]

    async def save_audit_log(
        self,
        *,
        trace_id: str,
        owner_type: str,
        owner_id: str,
        session_id: str,
        event_type: str,
        request_payload: dict,
        response_summary: str,
    ) -> AuditLogRecord:
        record = AuditLogRecord(
            trace_id=trace_id,
            owner_type=owner_type,
            owner_id=owner_id,
            session_id=session_id,
            event_type=event_type,
            request_payload=request_payload,
            response_summary=response_summary,
        )
        self.audit_logs.append(record)
        return record

    async def list_audit_logs(self, session_id: str) -> list[AuditLogRecord]:
        return [log for log in self.audit_logs if log.session_id == session_id]

    async def update_session_activity(self, session_id: str, message_increment: int) -> None:
        session = self.sessions.get(session_id)
        if not session:
            return
        session.last_active_at = datetime.now(timezone.utc).isoformat()
        session.message_count += message_increment

    async def next_stream_seq(self, session_id: str) -> int:
        current = self.stream_seq.get(session_id, 0) + 1
        self.stream_seq[session_id] = current
        return current

    @asynccontextmanager
    async def acquire_session_lock(self, session_id: str):
        lock = self.get_lock(session_id)
        if lock.locked():
            raise AppError(409, "SESSION_LOCKED", "同一会话有并发消息冲突", retryable=True)
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
