from collections import defaultdict
from datetime import datetime

from redis.asyncio import Redis

from app.core.config import settings
from app.core.errors import AppError


_RATE_COUNTER: dict[str, dict[str, int]] = defaultdict(dict)
_REDIS_CLIENT: Redis | None = None


def _minute_key() -> str:
    return datetime.utcnow().strftime("%Y%m%d%H%M")


def _use_redis_limit() -> bool:
    return settings.storage_backend.lower().strip() == "postgres"


async def _get_redis() -> Redis:
    global _REDIS_CLIENT
    if _REDIS_CLIENT is None:
        _REDIS_CLIENT = Redis.from_url(settings.redis_url, decode_responses=True)
    return _REDIS_CLIENT


async def _check_rate_limit_redis(owner_id: str) -> None:
    minute = _minute_key()
    key = f"rate:owner:{owner_id}:{minute}"
    client = await _get_redis()
    current = await client.incr(key)
    if current == 1:
        await client.expire(key, 60)
    if current > settings.rate_limit_per_minute:
        raise AppError(429, "RATE_LIMITED", "请求过于频繁", retryable=True)


async def _check_rate_limit_memory(owner_id: str) -> None:
    minute = _minute_key()
    owner_bucket = _RATE_COUNTER[owner_id]
    current = owner_bucket.get(minute, 0)

    if current >= settings.rate_limit_per_minute:
        raise AppError(429, "RATE_LIMITED", "请求过于频繁", retryable=True)

    owner_bucket[minute] = current + 1


async def check_rate_limit(owner_id: str) -> None:
    if _use_redis_limit():
        try:
            await _check_rate_limit_redis(owner_id)
            return
        except Exception:
            # Redis failure falls back to in-memory limiting for degraded safety.
            pass

    await _check_rate_limit_memory(owner_id)
