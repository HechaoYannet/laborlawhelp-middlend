from app.core.auth import Owner
from app.core.errors import AppError
from app.core.store import CaseRecord, store


async def create_case(owner: Owner, title: str, region_code: str) -> CaseRecord:
    return await store.create_case(owner.owner_type, owner.owner_id, title, region_code)


async def list_cases(owner: Owner) -> list[CaseRecord]:
    return await store.list_cases(owner.owner_type, owner.owner_id)


async def get_case(owner: Owner, case_id: str) -> CaseRecord:
    case_record = await store.get_case(case_id)
    if not case_record:
        raise AppError(404, "CASE_NOT_FOUND", "Case not found")
    if case_record.owner_id != owner.owner_id or case_record.owner_type != owner.owner_type:
        raise AppError(403, "FORBIDDEN", "无权访问该案件")
    return case_record
