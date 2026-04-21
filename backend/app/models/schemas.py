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


class Attachment(BaseModel):
    id: str
    name: str
    url: str
    mime_type: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    attachments: list[Attachment] = Field(default_factory=list)
    client_seq: int = Field(ge=0)
    locale: str | None = Field(default=None, max_length=32)
    policy_version: str | None = Field(default=None, max_length=64)
    client_capabilities: list[str] = Field(default_factory=list)


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    metadata: dict | None = None


class SmsSendRequest(BaseModel):
    phone: str


class SmsLoginRequest(BaseModel):
    phone: str
    code: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
