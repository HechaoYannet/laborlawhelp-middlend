from fastapi import FastAPI

from app.api.v1.routes import cases, chat, sessions
from app.core.errors import app_error_handler


def create_app() -> FastAPI:
    app = FastAPI(title="LaborLawHelp Middlend", version="0.1.0")
    app.include_router(cases.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.add_exception_handler(Exception, app_error_handler)
    return app


app = create_app()
