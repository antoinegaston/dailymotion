from collections.abc import AsyncIterator

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.config import get_settings
from src.logging import get_logger

logger = get_logger(__name__)


async def init_redis() -> tuple[Redis, str]:
    settings = get_settings()
    redis_url = str(settings.redis_url)
    redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        await redis.ping()
    except RedisError:
        logger.exception("Redis initialization failed")
        raise
    logger.info("Redis connection initialized")
    return redis, redis_url


async def get_redis(request: Request) -> AsyncIterator[Redis]:
    yield request.app.state.redis
