from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.db import init_pool
from app.schema import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await init_pool()
    async with app.state.pool.acquire() as conn:
        await create_tables(conn)
    yield
    await app.state.pool.close()


app = FastAPI(
    title="Dailymotion User Registration API", version="0.1.0", lifespan=lifespan
)
app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
