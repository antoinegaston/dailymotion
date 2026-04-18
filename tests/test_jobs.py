from asyncpg import Connection

from src.jobs.cleanup_unverified import delete_unverified_users


async def insert_user(
    conn: Connection, email: str, *, verified: bool, age_hours: int
) -> None:
    await conn.execute(
        "INSERT INTO users (email, password_hash, verified, created_at) "
        "VALUES ($1, 'hash', $2, NOW() - make_interval(hours => $3))",
        email,
        verified,
        age_hours,
    )


async def test_cleanup_deletes_only_old_unverified_users(db_conn: Connection):
    await insert_user(
        db_conn, "old-unverified@example.com", verified=False, age_hours=48
    )
    await insert_user(db_conn, "old-verified@example.com", verified=True, age_hours=48)
    await insert_user(
        db_conn, "new-unverified@example.com", verified=False, age_hours=1
    )
    await insert_user(db_conn, "new-verified@example.com", verified=True, age_hours=1)

    result = await delete_unverified_users(db_conn)

    assert result == "DELETE 1"
    remaining = {
        row["email"]
        for row in await db_conn.fetch("SELECT email FROM users ORDER BY email")
    }
    assert remaining == {
        "old-verified@example.com",
        "new-unverified@example.com",
        "new-verified@example.com",
    }


async def test_cleanup_is_noop_when_nothing_to_delete(db_conn: Connection):
    await insert_user(db_conn, "fresh@example.com", verified=False, age_hours=1)

    result = await delete_unverified_users(db_conn)

    assert result == "DELETE 0"
    count = await db_conn.fetchval("SELECT COUNT(*) FROM users")
    assert count == 1
