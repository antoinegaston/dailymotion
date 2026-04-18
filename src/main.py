from contextlib import asynccontextmanager

from fastapi import FastAPI
from limits.storage import RedisStorage
from limits.strategies import MovingWindowRateLimiter

from src.api import private_router, public_router
from src.logging import configure_logging, get_logger
from src.services.cache import init_redis
from src.services.db import create_tables, init_pool
from src.services.email import init_email_client

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("Starting API application")
    app.state.pool = await init_pool()
    app.state.redis, redis_url = await init_redis()
    app.state.limiter = MovingWindowRateLimiter(RedisStorage(redis_url))
    app.state.email_client = await init_email_client()
    async with app.state.pool.acquire() as conn:
        await create_tables(conn)
    logger.info("API startup complete")
    yield
    await app.state.pool.close()
    await app.state.redis.aclose()
    await app.state.email_client.aclose()
    logger.info("API shutdown complete")


app = FastAPI(title="User Registration API", version="0.1.0", lifespan=lifespan)
app.include_router(public_router, prefix="/api")
app.include_router(private_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
