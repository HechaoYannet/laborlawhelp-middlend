from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, retryable: bool = False, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, AppError):
        trace_id = str(uuid4())
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "trace_id": trace_id,
                "retryable": exc.retryable,
                "details": exc.details,
            },
        )

    trace_id = str(uuid4())
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "Internal server error",
            "trace_id": trace_id,
            "retryable": False,
            "details": {},
        },
    )
