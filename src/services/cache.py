from collections.abc import AsyncIterator

from fastapi import Request
from redis.asyncio import Redis

from src.config import get_settings


async def init_redis() -> tuple[Redis, str]:
    settings = get_settings()
    redis_url = str(settings.redis_url)
    redis = Redis.from_url(redis_url, decode_responses=True)
    await redis.ping()
    return redis, redis_url


async def get_redis(request: Request) -> AsyncIterator[Redis]:
    yield request.app.state.redis
