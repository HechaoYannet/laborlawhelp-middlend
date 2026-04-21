from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.case_session.router import router as case_session_router
from app.modules.chat.router import router as chat_router
from app.modules.playground.router import router as playground_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(case_session_router)
api_v1_router.include_router(chat_router)
api_v1_router.include_router(playground_router)
