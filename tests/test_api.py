import smtplib
from typing import Callable
from unittest.mock import AsyncMock, patch

import pytest
from asyncpg import Connection
from httpx import AsyncClient
from redis.exceptions import RedisError

from src.constants import EMAIL_VERIFICATION_BODY, EMAIL_VERIFICATION_SUBJECT


async def test_create_user_rejects_invalid_email(client: AsyncClient):
    payload = {"email": "invalid-email", "password": "password"}
    response = await client.post("/api/users", json=payload)
    assert response.status_code == 422


async def test_create_user_rejects_password_too_short(client: AsyncClient):
    payload = {"email": "too-short@example.com", "password": "short"}
    response = await client.post("/api/users", json=payload)
    assert response.status_code == 422


async def test_create_user_rejects_password_too_long(client: AsyncClient):
    payload = {"email": "too-long@example.com", "password": "a" * 129}
    response = await client.post("/api/users", json=payload)
    assert response.status_code == 422


async def test_create_user_success(
    client: AsyncClient, db_conn: Connection, redis_client_mock: AsyncMock
):
    payload = {"email": "success@example.com", "password": "password"}
    with (
        patch("src.helpers.send_email") as mock_send_email,
        patch("src.helpers.randbelow", return_value=1234),
    ):
        response = await client.post("/api/users", json=payload)
    assert response.status_code == 200
    user = await db_conn.fetchrow(
        "SELECT * FROM users WHERE email = $1", payload["email"]
    )
    assert user is not None
    assert user["email"] == payload["email"]
    assert user["password_hash"] != payload["password"]
    assert user["password_hash"].startswith("$argon2id$")
    mock_send_email.assert_called_once_with(
        payload["email"],
        EMAIL_VERIFICATION_SUBJECT,
        EMAIL_VERIFICATION_BODY.format(code=1234),
    )
    redis_client_mock.set.assert_awaited_once_with(
        f"verification_code:{payload['email']}", "1234", ex=60
    )


async def test_create_user_rejects_duplicate_email(
    client: AsyncClient, redis_client_mock: AsyncMock
):
    payload = {"email": "duplicate@example.com", "password": "password"}
    with patch("src.helpers.send_email") as mock_send_email:
        first_response = await client.post("/api/users", json=payload)
        assert first_response.status_code == 200

        # Reset mocks for second request
        mock_send_email.reset_mock()
        redis_client_mock.set.reset_mock()

        second_response = await client.post("/api/users", json=payload)
    assert second_response.status_code == 409
    assert second_response.json() == {"detail": "Email already registered"}
    mock_send_email.assert_not_called()
    redis_client_mock.set.assert_not_awaited()


async def test_create_user_rolls_back_when_redis_is_unavailable(
    client: AsyncClient, db_conn: Connection, redis_client_mock: AsyncMock
):
    payload = {"email": "redis-fails@example.com", "password": "password"}
    redis_client_mock.set.side_effect = RedisError("Redis unavailable")
    with patch("src.helpers.send_email") as mock_send_email:
        response = await client.post("/api/users", json=payload)
    assert response.status_code == 503
    assert response.json() == {"detail": "Verification storage unavailable"}
    user = await db_conn.fetchrow(
        "SELECT * FROM users WHERE email = $1", payload["email"]
    )
    assert user is None
    mock_send_email.assert_not_called()


async def test_create_user_rolls_back_when_email_delivery_fails(
    client: AsyncClient, db_conn: Connection, redis_client_mock: AsyncMock
):
    payload = {"email": "smtp-fail@example.com", "password": "password"}
    with patch(
        "src.helpers.send_email",
        side_effect=smtplib.SMTPException("Mock email delivery failed"),
    ):
        response = await client.post("/api/users", json=payload)
    assert response.status_code == 502
    assert response.json() == {"detail": "Verification email delivery failed"}
    user = await db_conn.fetchrow(
        "SELECT * FROM users WHERE email = $1", payload["email"]
    )
    assert user is None
    redis_client_mock.delete.assert_awaited_once_with(
        f"verification_code:{payload['email']}"
    )


@pytest.mark.parametrize("route", ["users/verify", "users/code"])
async def test_endpoint_rejects_unregistered_user(
    client: AsyncClient, auth_header: Callable, route: str
):
    headers = auth_header("missing@example.com", "password")
    response = await client.post(f"/api/{route}", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


@pytest.mark.parametrize("route", ["users/verify", "users/code"])
async def test_endpoint_rejects_wrong_password(
    client: AsyncClient, auth_header: Callable, route: str
):
    payload = {"email": "verify@example.com", "password": "password"}
    with patch("src.helpers.send_email"):
        create_response = await client.post("/api/users", json=payload)
    assert create_response.status_code == 200
    headers = auth_header(payload["email"], "wrong-password")
    response = await client.post(f"/api/{route}", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


async def test_verify_user_success(
    client: AsyncClient,
    db_conn: Connection,
    auth_header: Callable,
    redis_client_mock: AsyncMock,
):
    payload = {"email": "verify-success@example.com", "password": "password"}
    with patch("src.helpers.send_email"):
        create_response = await client.post("/api/users", json=payload)
    assert create_response.status_code == 200
    verified = await db_conn.fetchval(
        "SELECT verified FROM users WHERE email = $1", payload["email"]
    )
    assert verified is False
    code = "1234"
    redis_client_mock.get.return_value = code
    headers = auth_header(payload["email"], payload["password"])
    response = await client.post(
        "/api/users/verify", headers=headers, data={"code": code}
    )
    assert response.status_code == 200
    verified = await db_conn.fetchval(
        "SELECT verified FROM users WHERE email = $1", payload["email"]
    )
    assert verified is True


async def test_resend_verification_code_success(
    client: AsyncClient, auth_header: Callable, redis_client_mock: AsyncMock
):
    payload = {"email": "resend-success@example.com", "password": "password"}
    with (
        patch("src.helpers.send_email") as mock_send_email,
        patch("src.helpers.randbelow", return_value=1234),
    ):
        create_response = await client.post("/api/users", json=payload)
    assert create_response.status_code == 200
    mock_send_email.assert_called_once_with(
        payload["email"],
        EMAIL_VERIFICATION_SUBJECT,
        EMAIL_VERIFICATION_BODY.format(code=1234),
    )
    redis_client_mock.set.assert_awaited_once_with(
        f"verification_code:{payload['email']}", "1234", ex=60
    )
    redis_client_mock.reset_mock()
    headers = auth_header(payload["email"], payload["password"])
    with (
        patch("src.helpers.send_email") as mock_send_email,
        patch("src.helpers.randbelow", return_value=1235),
    ):
        response = await client.post("/api/users/code", headers=headers)
    assert response.status_code == 200
    mock_send_email.assert_called_once_with(
        payload["email"],
        EMAIL_VERIFICATION_SUBJECT,
        EMAIL_VERIFICATION_BODY.format(code=1235),
    )
    redis_client_mock.set.assert_awaited_once_with(
        f"verification_code:{payload['email']}", "1235", ex=60
    )
