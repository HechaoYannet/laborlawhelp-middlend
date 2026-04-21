from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Load .env before settings initialization so OpenHarness can read PKULAW_MCP_* vars.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.errors import AppError, app_error_handler


async def root() -> dict[str, str]:
    return {"service": settings.app_name, "version": settings.app_version, "status": "ok"}


async def shutdown_openharness() -> None:
    from app.adapters.openharness import openharness_client

    await openharness_client.close()


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods_list,
        allow_headers=settings.cors_allow_headers_list,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, app_error_handler)


def register_routes(app: FastAPI) -> None:
    app.include_router(api_v1_router, prefix="/api/v1")
    app.add_api_route("/", root, methods=["GET"])


def mount_static_assets(app: FastAPI) -> None:
    playground_dir = Path(__file__).resolve().parent / "static" / "playground"
    if playground_dir.exists():
        app.mount("/playground", StaticFiles(directory=playground_dir, html=True), name="playground")


def register_lifecycle_hooks(app: FastAPI) -> None:
    app.add_event_handler("shutdown", shutdown_openharness)


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    register_middleware(app)
    register_exception_handlers(app)
    register_routes(app)
    mount_static_assets(app)
    register_lifecycle_hooks(app)
    return app
