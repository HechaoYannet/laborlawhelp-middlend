from contextlib import asynccontextmanager

from app.modules.storage.records import AuditLogRecord, CaseRecord, MessageRecord, SessionRecord


class BaseStore:
    async def create_case(self, owner_type: str, owner_id: str, title: str, region_code: str) -> CaseRecord:
        raise NotImplementedError

    async def list_cases(self, owner_type: str, owner_id: str) -> list[CaseRecord]:
        raise NotImplementedError

    async def get_case(self, case_id: str) -> CaseRecord | None:
        raise NotImplementedError

    async def create_session(self, case_id: str, owner_type: str, owner_id: str) -> SessionRecord:
        raise NotImplementedError

    async def list_sessions(self, case_id: str, owner_type: str, owner_id: str) -> list[SessionRecord]:
        raise NotImplementedError

    async def get_session(self, session_id: str) -> SessionRecord | None:
        raise NotImplementedError

    async def end_session(self, session_id: str) -> SessionRecord | None:
        raise NotImplementedError

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_id: str | None = None,
        metadata: dict | None = None,
    ) -> MessageRecord:
        raise NotImplementedError

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
        raise NotImplementedError

    async def list_audit_logs(self, session_id: str) -> list[AuditLogRecord]:
        raise NotImplementedError

    async def list_messages(self, session_id: str) -> list[MessageRecord]:
        raise NotImplementedError

    async def update_session_activity(self, session_id: str, message_increment: int) -> None:
        raise NotImplementedError

    async def next_stream_seq(self, session_id: str) -> int:
        raise NotImplementedError

    @asynccontextmanager
    async def acquire_session_lock(self, session_id: str):
        raise NotImplementedError
