from dataclasses import dataclass

from fastapi import Header

from app.core.config import settings
from app.core.errors import AppError
from app.core.jwt_utils import decode_token


@dataclass
class Owner:
    owner_type: str
    owner_id: str


async def resolve_owner(
    x_anonymous_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Owner:
    auth_mode = settings.auth_mode.lower().strip()

    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise AppError(401, "UNAUTHORIZED", "Token invalid or expired")
        payload = decode_token(token, expected_type="access")
        return Owner(owner_type="user", owner_id=str(payload["sub"]))

    if auth_mode == "jwt":
        raise AppError(401, "UNAUTHORIZED", "Token invalid or expired")

    if x_anonymous_token:
        return Owner(owner_type="anonymous", owner_id=x_anonymous_token)

    raise AppError(401, "UNAUTHORIZED", "Missing owner token")
