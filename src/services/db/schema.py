from asyncpg import Connection

TABLES: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id          INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        email       TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
]


async def create_tables(conn: Connection) -> None:
    async with conn.transaction():
        for ddl in TABLES:
            await conn.execute(ddl)
