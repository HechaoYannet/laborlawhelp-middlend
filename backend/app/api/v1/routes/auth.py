from fastapi import APIRouter

from app.core.jwt_utils import create_access_token, create_refresh_token, decode_token
from app.models.schemas import RefreshTokenRequest, SmsLoginRequest, SmsSendRequest, TokenResponse

router = APIRouter(tags=["auth"])


@router.post("/auth/sms/send")
async def send_sms_code(payload: SmsSendRequest):
    return {
        "success": True,
        "phone": payload.phone,
        "message": "验证码已发送（开发环境模拟）",
    }


@router.post("/auth/sms/login", response_model=TokenResponse)
async def sms_login(payload: SmsLoginRequest):
    user_id = f"user-{payload.phone}"
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshTokenRequest):
    token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    return TokenResponse(access_token=create_access_token(str(token_payload["sub"])))


@router.post("/auth/logout")
async def logout():
    return {"success": True}
