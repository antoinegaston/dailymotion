from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.db import init_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await init_pool()
    yield
    await app.state.pool.close()


app = FastAPI(title="User Registration API", version="0.1.0", lifespan=lifespan)
app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}
