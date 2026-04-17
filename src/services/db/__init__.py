from collections.abc import AsyncIterator

from asyncpg import Connection, Pool, create_pool
from fastapi import Request

from src.config import get_settings
from src.services.db.schema import create_tables


async def init_pool() -> Pool:
    settings = get_settings()
    return await create_pool(dsn=str(settings.db_url))


async def get_db(request: Request) -> AsyncIterator[Connection]:
    pool: Pool = request.app.state.pool
    async with pool.acquire() as conn:
        async with conn.transaction():  # Rollback errored transactions
            yield conn


__all__ = ["init_pool", "get_db", "create_tables"]
