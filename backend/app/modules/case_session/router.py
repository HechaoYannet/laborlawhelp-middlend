from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.modules.auth import Owner, resolve_owner
from app.modules.case_session.schemas import (
    CaseResponse,
    CreateCaseRequest,
    CreateSessionResponse,
    EndSessionResponse,
    MessageResponse,
)
from app.modules.case_session.service import (
    create_case,
    create_session,
    end_session,
    get_case,
    list_cases,
    list_messages,
    list_sessions,
)

router = APIRouter()


@router.post("/cases", response_model=CaseResponse, status_code=201, tags=["cases"])
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


@router.get("/cases", response_model=list[CaseResponse], tags=["cases"])
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


@router.get("/cases/{case_id}", response_model=CaseResponse, tags=["cases"])
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


@router.post("/cases/{case_id}/sessions", response_model=CreateSessionResponse, status_code=201, tags=["cases"])
async def create_session_endpoint(case_id: str, owner: Owner = Depends(resolve_owner)):
    session = await create_session(owner, case_id)
    return CreateSessionResponse(
        id=session.id,
        case_id=session.case_id,
        status=session.status,
        openharness_session_id=session.openharness_session_id,
    )


@router.get("/cases/{case_id}/sessions", response_model=list[CreateSessionResponse], tags=["cases"])
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


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse], tags=["sessions"])
async def list_messages_endpoint(session_id: str, owner: Owner = Depends(resolve_owner)):
    records = await list_messages(owner, session_id)
    return [MessageResponse(id=m.id, role=m.role, content=m.content, created_at=m.created_at) for m in records]


@router.patch("/sessions/{session_id}/end", response_model=EndSessionResponse, tags=["sessions"])
async def end_session_endpoint(session_id: str, owner: Owner = Depends(resolve_owner)):
    session = await end_session(owner, session_id)
    return EndSessionResponse(
        id=session.id,
        status=session.status,
        ended_at=datetime.now(timezone.utc).isoformat(),
    )
