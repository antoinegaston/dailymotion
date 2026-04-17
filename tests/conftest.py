import base64
from types import SimpleNamespace
from typing import AsyncIterator
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from asyncpg import Connection, Pool, create_pool
from httpx import ASGITransport, AsyncClient
from src.services.cache import get_redis
from src.services.db import create_tables, get_db
from testcontainers.postgres import PostgresContainer

from src.config import get_settings


@pytest.fixture(scope="session")
def postgres_url() -> str:
    with PostgresContainer("postgres:16-alpine") as container:
        yield container.get_connection_url().replace("+psycopg2", "")


@pytest_asyncio.fixture(scope="session")
async def db_pool(postgres_url: str) -> AsyncIterator[Pool]:
    pool = await create_pool(dsn=postgres_url)
    async with pool.acquire() as conn:
        await create_tables(conn)
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def db_conn(db_pool: Pool) -> AsyncIterator[Connection]:
    async with db_pool.acquire() as conn:
        tr = conn.transaction()
        await tr.start()
        try:
            yield conn
        finally:
            await tr.rollback()


@pytest_asyncio.fixture
async def redis_client_mock() -> AsyncIterator[AsyncMock]:
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    yield redis


@pytest_asyncio.fixture
async def client(
    db_pool: Pool, db_conn: Connection, redis_client_mock: AsyncMock
) -> AsyncIterator[AsyncClient]:
    from src.main import app

    async def _override_get_db() -> AsyncIterator[Connection]:
        async with db_conn.transaction():
            yield db_conn

    async def _override_get_redis() -> AsyncIterator[AsyncMock]:
        yield redis_client_mock

    async def _override_get_settings() -> AsyncIterator[SimpleNamespace]:
        yield SimpleNamespace(verification_code_ttl_seconds=60)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis
    app.dependency_overrides[get_settings] = _override_get_settings
    app.state.limiter = Mock()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def auth_header():
    def inner(email: str, password: str) -> dict[str, str]:
        token = base64.b64encode(f"{email}:{password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}

    return inner
