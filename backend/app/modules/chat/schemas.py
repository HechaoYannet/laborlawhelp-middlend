from pydantic import BaseModel, Field


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
