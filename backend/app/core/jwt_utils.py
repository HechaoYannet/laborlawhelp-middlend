from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings
from app.core.errors import AppError


def create_access_token(user_id: str) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "typ": "access",
        "exp": expire_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": user_id,
        "typ": "refresh",
        "exp": expire_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise AppError(401, "UNAUTHORIZED", "Token invalid or expired") from exc

    token_type = payload.get("typ")
    if token_type != expected_type:
        raise AppError(401, "UNAUTHORIZED", "Token invalid or expired")

    if not payload.get("sub"):
        raise AppError(401, "UNAUTHORIZED", "Token invalid or expired")

    return payload
