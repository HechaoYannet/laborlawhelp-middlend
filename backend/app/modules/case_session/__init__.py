from app.modules.case_session.router import router
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
    get_session,
    list_cases,
    list_messages,
    list_sessions,
)

__all__ = [
    "CaseResponse",
    "CreateCaseRequest",
    "CreateSessionResponse",
    "EndSessionResponse",
    "MessageResponse",
    "create_case",
    "create_session",
    "end_session",
    "get_case",
    "get_session",
    "list_cases",
    "list_messages",
    "list_sessions",
    "router",
    "store",
]


def __getattr__(name: str):
    if name == "store":
        from app.modules.storage import get_store

        return get_store()
    raise AttributeError(name)
