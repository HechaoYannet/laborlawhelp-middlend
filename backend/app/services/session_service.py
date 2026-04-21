from app.modules.case_session import service as case_session_service


async def create_session(owner, case_id: str):
    return await case_session_service.create_session(owner, case_id)


async def list_sessions(owner, case_id: str):
    return await case_session_service.list_sessions(owner, case_id)


async def get_session(owner, session_id: str):
    return await case_session_service.get_session(owner, session_id)


async def list_messages(owner, session_id: str):
    return await case_session_service.list_messages(owner, session_id)


async def end_session(owner, session_id: str):
    return await case_session_service.end_session(owner, session_id)


def __getattr__(name: str):
    if name == "store":
        from app.modules.storage import get_store

        return get_store()
    raise AttributeError(name)
