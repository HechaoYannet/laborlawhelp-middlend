from app.modules.storage import (
    AuditLogRecord,
    BaseStore,
    CaseRecord,
    InMemoryStore,
    MessageRecord,
    PostgresRedisStore,
    SessionRecord,
    build_store,
    get_store,
    set_store,
)

__all__ = [
    "AuditLogRecord",
    "BaseStore",
    "CaseRecord",
    "InMemoryStore",
    "MessageRecord",
    "PostgresRedisStore",
    "SessionRecord",
    "build_store",
    "get_store",
    "set_store",
    "store",
]


def __getattr__(name: str):
    if name == "store":
        return get_store()
    raise AttributeError(name)
