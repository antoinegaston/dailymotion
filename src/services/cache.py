from collections.abc import AsyncIterator

from fastapi import Request
from redis.asyncio import Redis

from src.config import get_settings


async def init_redis() -> Redis:
    settings = get_settings()
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    await redis.ping()
    return redis


async def get_redis(request: Request) -> AsyncIterator[Redis]:
    yield request.app.state.redis
