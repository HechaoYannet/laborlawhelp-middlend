from fastapi import APIRouter

from app.modules.auth.schemas import RefreshTokenRequest, SmsLoginRequest, SmsSendRequest, TokenResponse
from app.modules.auth.service import login_with_sms, logout_user, refresh_access_token, send_sms_code

router = APIRouter(tags=["auth"])


@router.post("/auth/sms/send")
async def send_sms_code_endpoint(payload: SmsSendRequest):
    return await send_sms_code(payload)


@router.post("/auth/sms/login", response_model=TokenResponse)
async def sms_login_endpoint(payload: SmsLoginRequest):
    return await login_with_sms(payload)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(payload: RefreshTokenRequest):
    return await refresh_access_token(payload)


@router.post("/auth/logout")
async def logout_endpoint():
    return await logout_user()
