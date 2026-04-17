from contextlib import suppress
from secrets import randbelow
from typing import Annotated

from anyio import to_thread
from asyncpg import Connection, UniqueViolationError
from fastapi import APIRouter, Depends, Form, HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.config import Settings, get_settings
from src.constants import (
    EMAIL_VERIFICATION_BODY,
    EMAIL_VERIFICATION_KEY,
    EMAIL_VERIFICATION_SUBJECT,
)
from src.models import InternalUser, User
from src.services.auth import get_user, hasher
from src.services.cache import get_redis
from src.services.db import get_db
from src.services.email import SMTPError, send_email

router = APIRouter()


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
    except SMTPError as exc:
        with suppress(RedisError):  # Delete verification code if email delivery fails
            await redis.delete(verification_key)
        raise HTTPException(
            status_code=502, detail="Verification email delivery failed"
        ) from exc


@router.post("/users/verify")
async def verify_user(
    code: Annotated[str, Form(min_length=4, max_length=4)],
    user: InternalUser = Depends(get_user),
    db: Connection = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    # Reject if user is already verified
    if user.verified:
        raise HTTPException(status_code=400, detail="User already verified")

    verification_key = EMAIL_VERIFICATION_KEY.format(email=user.email)

    # Verify user
    try:
        verification_code = await redis.get(verification_key)
    except RedisError as exc:
        raise HTTPException(
            status_code=503, detail="Verification storage unavailable"
        ) from exc
    if verification_code != code:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    # Update user verification status
    await db.execute("UPDATE users SET verified = TRUE WHERE email = $1", user.email)
