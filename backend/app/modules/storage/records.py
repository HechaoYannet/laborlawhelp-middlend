from dataclasses import dataclass, field
from datetime import datetime, timezone


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


def to_iso(value: str | datetime) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value
