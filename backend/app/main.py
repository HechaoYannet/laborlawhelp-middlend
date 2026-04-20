import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Load .env into os.environ so OpenHarness settings can read PKULAW_MCP_* vars
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

from app.api.v1.routes import auth, cases, chat, playground, sessions
from app.core.config import settings
from app.core.errors import AppError, app_error_handler


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods_list,
        allow_headers=settings.cors_allow_headers_list,
    )
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(cases.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(playground.router, prefix="/api/v1")
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, app_error_handler)

    playground_dir = Path(__file__).resolve().parent / "static" / "playground"
    if playground_dir.exists():
        app.mount("/playground", StaticFiles(directory=playground_dir, html=True), name="playground")

    @app.get("/")
    async def root():
        return {"service": settings.app_name, "version": settings.app_version, "status": "ok"}

    @app.on_event("shutdown")
    async def _shutdown_oh():
        from app.adapters.openharness_client import openharness_client
        await openharness_client.close()

    return app


app = create_app()
