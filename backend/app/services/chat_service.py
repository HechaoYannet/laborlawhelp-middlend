from app.adapters.openharness import openharness_client
from app.modules.chat import service as chat_module


async def stream_chat(owner, session_id: str, request):
    async for event in chat_module.stream_chat(owner, session_id, request):
        yield event


def __getattr__(name: str):
    if name == "store":
        from app.modules.storage import get_store

        return get_store()
    if name == "openharness_client":
        return openharness_client
    raise AttributeError(name)
