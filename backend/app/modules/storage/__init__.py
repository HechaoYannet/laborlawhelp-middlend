from app.modules.storage.factory import build_store, get_store, set_store
from app.modules.storage.memory import InMemoryStore
from app.modules.storage.postgres import PostgresRedisStore
from app.modules.storage.protocol import BaseStore
from app.modules.storage.records import AuditLogRecord, CaseRecord, MessageRecord, SessionRecord

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
