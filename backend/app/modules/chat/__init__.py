from app.modules.chat.audit import AuditService
from app.modules.chat.router import router
from app.modules.chat.schemas import Attachment, ChatRequest
from app.modules.chat.service import openharness_client, stream_chat

__all__ = [
    "Attachment",
    "AuditService",
    "ChatRequest",
    "openharness_client",
    "router",
    "store",
    "stream_chat",
]


def __getattr__(name: str):
    if name == "store":
        from app.modules.storage import get_store

        return get_store()
    raise AttributeError(name)
