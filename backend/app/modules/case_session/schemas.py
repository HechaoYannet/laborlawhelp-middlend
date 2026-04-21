from pydantic import BaseModel, Field


class CreateCaseRequest(BaseModel):
    title: str = Field(default="未命名案件", max_length=200)
    region_code: str = Field(default="xian", max_length=20)


class CaseResponse(BaseModel):
    id: str
    owner_type: str
    created_at: str
    title: str
    region_code: str
    status: str


class CreateSessionResponse(BaseModel):
    id: str
    case_id: str
    status: str
    openharness_session_id: str | None = None


class EndSessionResponse(BaseModel):
    id: str
    status: str
    ended_at: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    metadata: dict | None = None
