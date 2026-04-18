from collections import defaultdict
from datetime import datetime

from app.core.config import settings
from app.core.errors import AppError


_RATE_COUNTER: dict[str, dict[str, int]] = defaultdict(dict)


def _minute_key() -> str:
    return datetime.utcnow().strftime("%Y%m%d%H%M")


async def check_rate_limit(owner_id: str) -> None:
    minute = _minute_key()
    owner_bucket = _RATE_COUNTER[owner_id]
    current = owner_bucket.get(minute, 0)

    if current >= settings.rate_limit_per_minute:
        raise AppError(429, "RATE_LIMITED", "请求过于频繁", retryable=True)

    owner_bucket[minute] = current + 1
