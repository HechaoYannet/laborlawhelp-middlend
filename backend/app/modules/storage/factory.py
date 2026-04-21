from app.core.config import settings
from app.modules.storage.memory import InMemoryStore
from app.modules.storage.postgres import PostgresRedisStore
from app.modules.storage.protocol import BaseStore

_store: BaseStore | None = None


def build_store() -> BaseStore:
    backend = settings.storage_backend.lower().strip()
    if backend == "postgres":
        return PostgresRedisStore()
    return InMemoryStore()


def get_store() -> BaseStore:
    global _store
    if _store is None:
        _store = build_store()
    return _store


def set_store(data_store: BaseStore) -> BaseStore:
    global _store
    _store = data_store
    return _store
