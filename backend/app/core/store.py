from dataclasses import dataclass, field
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import asyncio
import json
from uuid import UUID
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import settings
from app.core.errors import AppError


@dataclass
class CaseRecord:
    id: str
    owner_type: str
    owner_id: str
    title: str
    region_code: str
    status: str = "active"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SessionRecord:
    id: str
    case_id: str
    owner_type: str
    owner_id: str
    status: str = "active"
    openharness_session_id: str | None = None
    message_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_active_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class MessageRecord:
    id: str
    session_id: str
    role: str
    content: str
    metadata: dict | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AuditLogRecord:
    trace_id: str
    owner_type: str
    owner_id: str
    session_id: str
    event_type: str
    request_payload: dict
    response_summary: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _to_iso(value: str | datetime) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


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
        return [c for c in self.cases.values() if c.owner_type == owner_type and c.owner_id == owner_id]

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
            s
            for s in self.sessions.values()
            if s.case_id == case_id and s.owner_type == owner_type and s.owner_id == owner_id
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
        msg = MessageRecord(
            id=message_id or self.new_id(),
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata,
        )
        self.messages.append(msg)
        return msg

    async def list_messages(self, session_id: str) -> list[MessageRecord]:
        return [m for m in self.messages if m.session_id == session_id]

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


class PostgresRedisStore(BaseStore):
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._redis: Redis | None = None

    def _db_url(self) -> str:
        if settings.database_url.startswith("postgresql+asyncpg://"):
            return settings.database_url
        if settings.database_url.startswith("postgresql://"):
            return settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return settings.database_url

    async def _engine_ref(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_async_engine(self._db_url(), pool_pre_ping=True)
        return self._engine

    async def _redis_ref(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def create_case(self, owner_type: str, owner_id: str, title: str, region_code: str) -> CaseRecord:
        case_id = str(uuid4())
        user_id = owner_id if owner_type == "user" else None
        anonymous_id = owner_id if owner_type == "anonymous" else None
        engine = await self._engine_ref()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO cases (id, user_id, anonymous_id, owner_type, title, region_code, status, created_at, updated_at)
                    VALUES (:id, :user_id, :anonymous_id, :owner_type, :title, :region_code, 'active', NOW(), NOW())
                    """
                ),
                {
                    "id": case_id,
                    "user_id": user_id,
                    "anonymous_id": anonymous_id,
                    "owner_type": owner_type,
                    "title": title,
                    "region_code": region_code,
                },
            )
        return CaseRecord(id=case_id, owner_type=owner_type, owner_id=owner_id, title=title, region_code=region_code)

    async def list_cases(self, owner_type: str, owner_id: str) -> list[CaseRecord]:
        engine = await self._engine_ref()
        user_id = owner_id if owner_type == "user" else None
        anonymous_id = owner_id if owner_type == "anonymous" else None
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT id, owner_type, title, region_code, status, created_at, updated_at
                    FROM cases
                    WHERE owner_type = :owner_type
                      AND ((:user_id IS NOT NULL AND user_id = :user_id)
                           OR (:anonymous_id IS NOT NULL AND anonymous_id = :anonymous_id))
                    ORDER BY updated_at DESC
                    """
                ),
                {"owner_type": owner_type, "user_id": user_id, "anonymous_id": anonymous_id},
            )
            rows = result.mappings().all()
        return [
            CaseRecord(
                id=str(row["id"]),
                owner_type=str(row["owner_type"]),
                owner_id=owner_id,
                title=str(row["title"]),
                region_code=str(row["region_code"]),
                status=str(row["status"]),
                created_at=_to_iso(row["created_at"]),
                updated_at=_to_iso(row["updated_at"]),
            )
            for row in rows
        ]

    async def get_case(self, case_id: str) -> CaseRecord | None:
        engine = await self._engine_ref()
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT id, user_id, anonymous_id, owner_type, title, region_code, status, created_at, updated_at
                    FROM cases
                    WHERE id = :id
                    """
                ),
                {"id": case_id},
            )
            row = result.mappings().first()
        if not row:
            return None
        owner_id = str(row["user_id"] or row["anonymous_id"])
        return CaseRecord(
            id=str(row["id"]),
            owner_type=str(row["owner_type"]),
            owner_id=owner_id,
            title=str(row["title"]),
            region_code=str(row["region_code"]),
            status=str(row["status"]),
            created_at=_to_iso(row["created_at"]),
            updated_at=_to_iso(row["updated_at"]),
        )

    async def create_session(self, case_id: str, owner_type: str, owner_id: str) -> SessionRecord:
        session_id = str(uuid4())
        openharness_session_id = str(uuid4())
        user_id = owner_id if owner_type == "user" else None
        anonymous_id = owner_id if owner_type == "anonymous" else None
        engine = await self._engine_ref()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO sessions (
                        id,
                        case_id,
                        user_id,
                        anonymous_id,
                        openharness_session_id,
                        status,
                        message_count,
                        created_at,
                        last_active_at
                    )
                    VALUES (
                        :id,
                        :case_id,
                        :user_id,
                        :anonymous_id,
                        :openharness_session_id,
                        'active',
                        0,
                        NOW(),
                        NOW()
                    )
                    """
                ),
                {
                    "id": session_id,
                    "case_id": case_id,
                    "user_id": user_id,
                    "anonymous_id": anonymous_id,
                    "openharness_session_id": openharness_session_id,
                },
            )
        return SessionRecord(
            id=session_id,
            case_id=case_id,
            owner_type=owner_type,
            owner_id=owner_id,
            openharness_session_id=openharness_session_id,
        )

    async def list_sessions(self, case_id: str, owner_type: str, owner_id: str) -> list[SessionRecord]:
        engine = await self._engine_ref()
        user_id = owner_id if owner_type == "user" else None
        anonymous_id = owner_id if owner_type == "anonymous" else None
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT id, case_id, user_id, anonymous_id, openharness_session_id, status, message_count, created_at, last_active_at
                    FROM sessions
                    WHERE case_id = :case_id
                      AND ((:user_id IS NOT NULL AND user_id = :user_id)
                           OR (:anonymous_id IS NOT NULL AND anonymous_id = :anonymous_id))
                    ORDER BY created_at DESC
                    """
                ),
                {"case_id": case_id, "user_id": user_id, "anonymous_id": anonymous_id},
            )
            rows = result.mappings().all()
        return [
            SessionRecord(
                id=str(row["id"]),
                case_id=str(row["case_id"]),
                owner_type=owner_type,
                owner_id=owner_id,
                status=str(row["status"]),
                openharness_session_id=row["openharness_session_id"],
                message_count=int(row["message_count"]),
                created_at=_to_iso(row["created_at"]),
                last_active_at=_to_iso(row["last_active_at"]),
            )
            for row in rows
        ]

    async def get_session(self, session_id: str) -> SessionRecord | None:
        engine = await self._engine_ref()
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT id, case_id, user_id, anonymous_id, openharness_session_id, status, message_count, created_at, last_active_at
                    FROM sessions
                    WHERE id = :id
                    """
                ),
                {"id": session_id},
            )
            row = result.mappings().first()
        if not row:
            return None
        owner_type = "user" if row["user_id"] else "anonymous"
        owner_id = str(row["user_id"] or row["anonymous_id"])
        return SessionRecord(
            id=str(row["id"]),
            case_id=str(row["case_id"]),
            owner_type=owner_type,
            owner_id=owner_id,
            status=str(row["status"]),
            openharness_session_id=row["openharness_session_id"],
            message_count=int(row["message_count"]),
            created_at=_to_iso(row["created_at"]),
            last_active_at=_to_iso(row["last_active_at"]),
        )

    async def end_session(self, session_id: str) -> SessionRecord | None:
        engine = await self._engine_ref()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE sessions
                    SET status = 'ended', last_active_at = NOW()
                    WHERE id = :id
                    """
                ),
                {"id": session_id},
            )
        return await self.get_session(session_id)

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_id: str | None = None,
        metadata: dict | None = None,
    ) -> MessageRecord:
        mid = message_id or str(uuid4())
        engine = await self._engine_ref()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO messages (id, session_id, role, content, metadata, created_at)
                    VALUES (:id, :session_id, :role, :content, CAST(:metadata AS JSONB), NOW())
                    """
                ),
                {
                    "id": mid,
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                    "metadata": None if metadata is None else json.dumps(metadata, ensure_ascii=False),
                },
            )
        return MessageRecord(id=mid, session_id=session_id, role=role, content=content, metadata=metadata)

    async def list_messages(self, session_id: str) -> list[MessageRecord]:
        engine = await self._engine_ref()
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT id, session_id, role, content, metadata, created_at
                    FROM messages
                    WHERE session_id = :session_id
                    ORDER BY created_at ASC
                    """
                ),
                {"session_id": session_id},
            )
            rows = result.mappings().all()
        return [
            MessageRecord(
                id=str(row["id"]),
                session_id=str(row["session_id"]),
                role=str(row["role"]),
                content=str(row["content"]),
                metadata=row["metadata"],
                created_at=_to_iso(row["created_at"]),
            )
            for row in rows
        ]

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
        engine = await self._engine_ref()
        user_id: str | None = None
        anonymous_id: str | None = None
        if owner_type == "user":
            try:
                user_id = str(UUID(owner_id))
            except ValueError:
                user_id = None
        else:
            anonymous_id = owner_id
        if owner_type == "user" and user_id is None:
            anonymous_id = owner_id

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO audit_logs (
                        trace_id,
                        user_id,
                        anonymous_id,
                        session_id,
                        event_type,
                        request_payload,
                        response_summary,
                        created_at
                    )
                    VALUES (
                        CAST(:trace_id AS UUID),
                        CAST(:user_id AS UUID),
                        :anonymous_id,
                        CAST(:session_id AS UUID),
                        :event_type,
                        CAST(:request_payload AS JSONB),
                        :response_summary,
                        NOW()
                    )
                    """
                ),
                {
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "anonymous_id": anonymous_id,
                    "session_id": session_id,
                    "event_type": event_type,
                    "request_payload": json.dumps(request_payload, ensure_ascii=False),
                    "response_summary": response_summary,
                },
            )
        return AuditLogRecord(
            trace_id=trace_id,
            owner_type=owner_type,
            owner_id=owner_id,
            session_id=session_id,
            event_type=event_type,
            request_payload=request_payload,
            response_summary=response_summary,
        )

    async def list_audit_logs(self, session_id: str) -> list[AuditLogRecord]:
        engine = await self._engine_ref()
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT trace_id, user_id, anonymous_id, session_id, event_type, request_payload, response_summary, created_at
                    FROM audit_logs
                    WHERE session_id = CAST(:session_id AS UUID)
                    ORDER BY created_at ASC
                    """
                ),
                {"session_id": session_id},
            )
            rows = result.mappings().all()

        records = []
        for row in rows:
            owner_type = "user" if row["user_id"] else "anonymous"
            owner_id = str(row["user_id"] or row["anonymous_id"] or "")
            request_payload = row["request_payload"]
            if isinstance(request_payload, str):
                request_payload = json.loads(request_payload)
            records.append(
                AuditLogRecord(
                    trace_id=str(row["trace_id"]),
                    owner_type=owner_type,
                    owner_id=owner_id,
                    session_id=str(row["session_id"]),
                    event_type=str(row["event_type"]),
                    request_payload=request_payload if isinstance(request_payload, dict) else {},
                    response_summary=str(row["response_summary"] or ""),
                    created_at=_to_iso(row["created_at"]),
                )
            )
        return records

    async def update_session_activity(self, session_id: str, message_increment: int) -> None:
        engine = await self._engine_ref()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    UPDATE sessions
                    SET message_count = message_count + :inc,
                        last_active_at = NOW()
                    WHERE id = :id
                    """
                ),
                {"id": session_id, "inc": message_increment},
            )

    async def next_stream_seq(self, session_id: str) -> int:
        redis = await self._redis_ref()
        return int(await redis.incr(f"session:{session_id}:stream:seq"))

    @asynccontextmanager
    async def acquire_session_lock(self, session_id: str):
        redis = await self._redis_ref()
        lock = redis.lock(
            f"session:{session_id}:lock",
            timeout=settings.session_lock_timeout_seconds,
            blocking=False,
        )
        acquired = await lock.acquire()
        if not acquired:
            raise AppError(409, "SESSION_LOCKED", "同一会话有并发消息冲突", retryable=True)
        try:
            yield
        finally:
            try:
                await lock.release()
            except Exception:
                pass


def build_store() -> BaseStore:
    backend = settings.storage_backend.lower().strip()
    if backend == "postgres":
        return PostgresRedisStore()
    return InMemoryStore()


store = build_store()
