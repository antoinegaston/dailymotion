from contextlib import suppress
from secrets import randbelow

from anyio import to_thread
from argon2 import PasswordHasher
from asyncpg import Connection, UniqueViolationError
from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.config import Settings, get_settings
from src.constants import (
    EMAIL_VERIFICATION_BODY,
    EMAIL_VERIFICATION_KEY,
    EMAIL_VERIFICATION_SUBJECT,
)
from src.models import User
from src.services.cache import get_redis
from src.services.db import get_db
from src.services.email import send_email

router = APIRouter()
hasher = PasswordHasher()


@router.post("/users")
async def create_user(
    user: User,
    db: Connection = Depends(get_db),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
):
    verification_key = EMAIL_VERIFICATION_KEY.format(email=user.email)
    verification_code = f"{randbelow(10000):04d}"
    password_hash = await to_thread.run_sync(
        hasher.hash, user.password.get_secret_value()
    )

    # Insert user into database
    try:
        async with db.transaction():
            await db.execute(
                "INSERT INTO users (email, password_hash) VALUES ($1, $2)",
                user.email,
                password_hash,
            )
    except UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc

    # Store verification code in Redis
    try:
        await redis.set(
            verification_key,
            verification_code,
            ex=settings.verification_code_ttl_seconds,
        )
    except RedisError as exc:
        with suppress(Exception):  # Rollback user insertion if Redis is unavailable
            await db.execute("DELETE FROM users WHERE email = $1", user.email)
        raise HTTPException(
            status_code=503, detail="Verification storage unavailable"
        ) from exc

    # Send verification email
    try:
        await to_thread.run_sync(
            send_email,
            user.email,
            EMAIL_VERIFICATION_SUBJECT,
            EMAIL_VERIFICATION_BODY.format(code=verification_code),
        )
    except HTTPException as exc:
        with suppress(Exception):  # Rollback user insertion if email delivery fails
            await db.execute("DELETE FROM users WHERE email = $1", user.email)
        with suppress(RedisError):  # Delete verification code if email delivery fails
            await redis.delete(verification_key)
        raise HTTPException(
            status_code=502, detail="Verification email delivery failed"
        ) from exc
