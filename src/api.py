from typing import Annotated

from anyio import to_thread
from asyncpg import Connection, UniqueViolationError
from fastapi import APIRouter, Depends, Form, HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.config import Settings, get_settings
from src.constants import EMAIL_VERIFICATION_KEY
from src.helpers import issue_verification_code
from src.models import InternalUser, User
from src.services.auth import get_user, hasher
from src.services.cache import get_redis
from src.services.db import get_db
from src.services.security import limit_rate

public_router = APIRouter()
private_router = APIRouter(dependencies=[Depends(get_user)])


@public_router.post("/users", dependencies=[Depends(limit_rate("1/hour"))])
async def create_user(
    user: User,
    db: Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
):
    password_hash = await to_thread.run_sync(
        hasher.hash, user.password.get_secret_value()
    )
    try:
        await db.execute(
            "INSERT INTO users (email, password_hash) VALUES ($1, $2)",
            user.email,
            password_hash,
        )
    except UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc
    await issue_verification_code(user.email, settings, redis)


@private_router.post("/users/verify", dependencies=[Depends(limit_rate("1/minute"))])
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


@private_router.post("/users/code", dependencies=[Depends(limit_rate("1/minute"))])
async def resend_verification_code(
    user: InternalUser = Depends(get_user),
    settings: Settings = Depends(get_settings),
    redis: Redis = Depends(get_redis),
):
    await issue_verification_code(user.email, settings, redis)
