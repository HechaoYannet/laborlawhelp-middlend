from fastapi import FastAPI

from app.api.v1.routes import auth, cases, chat, sessions
from app.core.config import settings
from app.core.errors import AppError, app_error_handler


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(cases.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, app_error_handler)
    return app


app = create_app()
