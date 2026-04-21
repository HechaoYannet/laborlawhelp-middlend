import json
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import settings
from app.core.errors import AppError
from app.modules.storage.protocol import BaseStore
from app.modules.storage.records import AuditLogRecord, CaseRecord, MessageRecord, SessionRecord, to_iso


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
                created_at=to_iso(row["created_at"]),
                updated_at=to_iso(row["updated_at"]),
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
            created_at=to_iso(row["created_at"]),
            updated_at=to_iso(row["updated_at"]),
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
                created_at=to_iso(row["created_at"]),
                last_active_at=to_iso(row["last_active_at"]),
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
            created_at=to_iso(row["created_at"]),
            last_active_at=to_iso(row["last_active_at"]),
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
        message_id = message_id or str(uuid4())
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
                    "id": message_id,
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                    "metadata": None if metadata is None else json.dumps(metadata, ensure_ascii=False),
                },
            )
        return MessageRecord(id=message_id, session_id=session_id, role=role, content=content, metadata=metadata)

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
                created_at=to_iso(row["created_at"]),
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
                    created_at=to_iso(row["created_at"]),
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
