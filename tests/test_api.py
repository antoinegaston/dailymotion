from asyncpg import Connection
from httpx import AsyncClient


async def test_create_user_rejects_invalid_email(client: AsyncClient):
    payload = {"email": "invalid-email", "password": "password"}
    response = await client.post("/api/users", json=payload)
    assert response.status_code == 422


async def test_create_user_rejects_short_password(client: AsyncClient):
    payload = {"email": "short@example.com", "password": "short"}
    response = await client.post("/api/users", json=payload)
    assert response.status_code == 422


async def test_create_user_rejects_password_too_long(client: AsyncClient):
    payload = {"email": "toolong@example.com", "password": "a" * 129}
    response = await client.post("/api/users", json=payload)
    assert response.status_code == 422


async def test_create_user_success(client: AsyncClient, db_conn: Connection):
    payload = {"email": "test@example.com", "password": "password"}
    response = await client.post("/api/users", json=payload)
    assert response.status_code == 200
    user = await db_conn.fetchrow(
        "SELECT * FROM users WHERE email = $1", payload["email"]
    )
    assert user is not None
    assert user["email"] == payload["email"]
    assert user["password_hash"] != payload["password"]
    assert user["password_hash"].startswith("$argon2id$")


async def test_create_user_rejects_duplicate_email(client: AsyncClient):
    payload = {"email": "duplicate@example.com", "password": "password"}
    first_response = await client.post("/api/users", json=payload)
    second_response = await client.post("/api/users", json=payload)
    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json() == {"detail": "Email already registered"}
