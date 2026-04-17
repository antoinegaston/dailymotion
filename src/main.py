from contextlib import asynccontextmanager

from fastapi import FastAPI
from limits.storage import RedisStorage
from limits.strategies import MovingWindowRateLimiter

from src.api import private_router, public_router
from src.services.cache import init_redis
from src.services.db import create_tables, init_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await init_pool()
    app.state.redis, redis_url = await init_redis()
    app.state.limiter = MovingWindowRateLimiter(RedisStorage(redis_url))
    async with app.state.pool.acquire() as conn:
        await create_tables(conn)
    yield
    await app.state.pool.close()
    await app.state.redis.aclose()


app = FastAPI(title="User Registration API", version="0.1.0", lifespan=lifespan)
app.include_router(public_router, prefix="/api")
app.include_router(private_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
