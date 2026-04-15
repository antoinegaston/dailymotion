from contextlib import asynccontextmanager
from typing import AsyncIterator

import pytest
import pytest_asyncio
from asyncpg import Connection, Pool, create_pool
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from testcontainers.postgres import PostgresContainer

from app.db import get_db


@pytest.fixture(scope="session")
def postgres_url() -> str:
    with PostgresContainer("postgres:16-alpine") as container:
        yield container.get_connection_url().replace("+psycopg2", "")


@pytest_asyncio.fixture(scope="session")
async def db_pool(postgres_url: str) -> AsyncIterator[Pool]:
    pool = await create_pool(dsn=postgres_url)
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def db_conn(db_pool: Pool) -> AsyncIterator[Connection]:
    async with db_pool.acquire() as conn:
        yield conn


@pytest_asyncio.fixture
async def client(db_pool: Pool) -> AsyncIterator[AsyncClient]:
    from app.main import app

    async def _override_get_db() -> AsyncIterator[Connection]:
        async with db_pool.acquire() as conn:
            yield conn

    app.dependency_overrides[get_db] = _override_get_db

    @asynccontextmanager
    async def _test_lifespan(_app: FastAPI):
        _app.state.pool = db_pool
        yield

    app.router.lifespan_context = _test_lifespan

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test/api"
    ) as c:
        yield c

    app.dependency_overrides.clear()
