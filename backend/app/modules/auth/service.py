from app.modules.auth.schemas import RefreshTokenRequest, SmsLoginRequest, SmsSendRequest, TokenResponse
from app.modules.auth.tokens import create_access_token, create_refresh_token, decode_token


async def send_sms_code(payload: SmsSendRequest) -> dict[str, str | bool]:
    return {
        "success": True,
        "phone": payload.phone,
        "message": "验证码已发送（开发环境模拟）",
    }


async def login_with_sms(payload: SmsLoginRequest) -> TokenResponse:
    user_id = f"user-{payload.phone}"
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


async def refresh_access_token(payload: RefreshTokenRequest) -> TokenResponse:
    token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    return TokenResponse(access_token=create_access_token(str(token_payload["sub"])))


async def logout_user() -> dict[str, bool]:
    return {"success": True}
