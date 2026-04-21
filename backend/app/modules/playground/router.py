from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["playground"])


@router.get("/playground/runtime")
async def get_playground_runtime():
    openharness_mode = "mock" if settings.oh_use_mock else settings.oh_mode
    return {
        "app_name": settings.app_name,
        "app_version": settings.app_version,
        "auth_mode": settings.auth_mode,
        "storage_backend": settings.storage_backend,
        "openharness_mode": openharness_mode,
        "workflow": settings.oh_default_workflow,
        "local_rule_fallback": settings.app_enable_local_rule_fallback,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "stream_path": "/api/v1/sessions/{session_id}/chat/stream",
    }
