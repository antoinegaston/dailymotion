from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api import router
from src.services.cache import init_redis
from src.services.db import create_tables, init_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await init_pool()
    app.state.redis = await init_redis()
    async with app.state.pool.acquire() as conn:
        await create_tables(conn)
    yield
    await app.state.pool.close()
    await app.state.redis.aclose()


app = FastAPI(title="User Registration API", version="0.1.0", lifespan=lifespan)
app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
