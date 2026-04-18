from fastapi import APIRouter, Depends

from app.core.auth import Owner, resolve_owner
from app.models.schemas import CaseResponse, CreateCaseRequest, CreateSessionResponse
from app.services.case_service import create_case, get_case, list_cases
from app.services.session_service import create_session, list_sessions

router = APIRouter(tags=["cases"])


@router.post("/cases", response_model=CaseResponse, status_code=201)
async def create_case_endpoint(payload: CreateCaseRequest, owner: Owner = Depends(resolve_owner)):
    record = await create_case(owner, payload.title, payload.region_code)
    return CaseResponse(
        id=record.id,
        owner_type=record.owner_type,
        created_at=record.created_at,
        title=record.title,
        region_code=record.region_code,
        status=record.status,
    )


@router.get("/cases", response_model=list[CaseResponse])
async def list_cases_endpoint(owner: Owner = Depends(resolve_owner)):
    records = await list_cases(owner)
    return [
        CaseResponse(
            id=r.id,
            owner_type=r.owner_type,
            created_at=r.created_at,
            title=r.title,
            region_code=r.region_code,
            status=r.status,
        )
        for r in records
    ]


@router.get("/cases/{case_id}", response_model=CaseResponse)
async def get_case_endpoint(case_id: str, owner: Owner = Depends(resolve_owner)):
    record = await get_case(owner, case_id)
    return CaseResponse(
        id=record.id,
        owner_type=record.owner_type,
        created_at=record.created_at,
        title=record.title,
        region_code=record.region_code,
        status=record.status,
    )


@router.post("/cases/{case_id}/sessions", response_model=CreateSessionResponse, status_code=201)
async def create_session_endpoint(case_id: str, owner: Owner = Depends(resolve_owner)):
    session = await create_session(owner, case_id)
    return CreateSessionResponse(
        id=session.id,
        case_id=session.case_id,
        status=session.status,
        openharness_session_id=session.openharness_session_id,
    )


@router.get("/cases/{case_id}/sessions", response_model=list[CreateSessionResponse])
async def list_sessions_endpoint(case_id: str, owner: Owner = Depends(resolve_owner)):
    records = await list_sessions(owner, case_id)
    return [
        CreateSessionResponse(
            id=s.id,
            case_id=s.case_id,
            status=s.status,
            openharness_session_id=s.openharness_session_id,
        )
        for s in records
    ]
