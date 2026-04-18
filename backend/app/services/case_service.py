from app.core.auth import Owner
from app.core.errors import AppError
from app.core.store import CaseRecord, store


def create_case(owner: Owner, title: str, region_code: str) -> CaseRecord:
    case_id = store.new_id()
    record = CaseRecord(
        id=case_id,
        owner_type=owner.owner_type,
        owner_id=owner.owner_id,
        title=title,
        region_code=region_code,
    )
    store.cases[case_id] = record
    return record


def list_cases(owner: Owner) -> list[CaseRecord]:
    return [c for c in store.cases.values() if c.owner_id == owner.owner_id and c.owner_type == owner.owner_type]


def get_case(owner: Owner, case_id: str) -> CaseRecord:
    case_record = store.cases.get(case_id)
    if not case_record:
        raise AppError(404, "CASE_NOT_FOUND", "Case not found")
    if case_record.owner_id != owner.owner_id or case_record.owner_type != owner.owner_type:
        raise AppError(403, "FORBIDDEN", "无权访问该案件")
    return case_record
