from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4


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
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InMemoryStore:
    def __init__(self) -> None:
        self.cases: dict[str, CaseRecord] = {}
        self.sessions: dict[str, SessionRecord] = {}
        self.messages: list[MessageRecord] = []
        self.session_locks: dict[str, Lock] = {}

    def new_id(self) -> str:
        return str(uuid4())

    def get_lock(self, session_id: str) -> Lock:
        if session_id not in self.session_locks:
            self.session_locks[session_id] = Lock()
        return self.session_locks[session_id]


store = InMemoryStore()
