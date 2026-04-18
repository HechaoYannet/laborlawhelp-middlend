from dataclasses import dataclass

from fastapi import Header

from app.core.errors import AppError


@dataclass
class Owner:
    owner_type: str
    owner_id: str


async def resolve_owner(
    x_anonymous_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Owner:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise AppError(401, "UNAUTHORIZED", "Token invalid or expired")
        return Owner(owner_type="user", owner_id="user-demo")

    if x_anonymous_token:
        return Owner(owner_type="anonymous", owner_id=x_anonymous_token)

    raise AppError(401, "UNAUTHORIZED", "Missing owner token")
