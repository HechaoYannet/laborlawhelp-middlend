from app.modules.case_session import service as case_session_service


async def create_case(owner, title: str, region_code: str):
    return await case_session_service.create_case(owner, title, region_code)


async def list_cases(owner):
    return await case_session_service.list_cases(owner)


async def get_case(owner, case_id: str):
    return await case_session_service.get_case(owner, case_id)


def __getattr__(name: str):
    if name == "store":
        from app.modules.storage import get_store

        return get_store()
    raise AttributeError(name)
