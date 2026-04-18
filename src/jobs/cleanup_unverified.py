import asyncio

from asyncpg import Connection, connect

from src.config import get_settings
from src.logging import configure_logging, get_logger

logger = get_logger(__name__)


async def delete_unverified_users(conn: Connection) -> str:
    return await conn.execute(
        "DELETE FROM users "
        "WHERE verified = FALSE "
        "AND created_at < NOW() - INTERVAL '1 day'"
    )


async def main() -> None:
    configure_logging()
    logger.info("Starting unverified user cleanup")
    settings = get_settings()
    conn = await connect(dsn=str(settings.db_url))
    try:
        result = await delete_unverified_users(conn)
    finally:
        await conn.close()
    logger.info("Unverified user cleanup finished (%s)", result)


if __name__ == "__main__":
    asyncio.run(main())
