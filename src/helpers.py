from contextlib import suppress
from secrets import randbelow

from anyio import to_thread
from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError
from src.services.email import SMTPError, send_email

from src.config import Settings
from src.constants import (
    EMAIL_VERIFICATION_BODY,
    EMAIL_VERIFICATION_KEY,
    EMAIL_VERIFICATION_SUBJECT,
)
from src.logging import get_logger

logger = get_logger(__name__)


async def issue_verification_code(email: str, settings: Settings, redis: Redis):
    verification_key = EMAIL_VERIFICATION_KEY.format(email=email)
    verification_code = f"{randbelow(10000):04d}"

    # Store verification code in Redis
    try:
        await redis.set(
            verification_key,
            verification_code,
            ex=settings.verification_code_ttl_seconds,
        )
    except RedisError as exc:
        logger.exception("Failed to store verification code in Redis")
        raise HTTPException(
            status_code=503, detail="Verification storage unavailable"
        ) from exc

    # Send verification email
    try:
        await to_thread.run_sync(
            send_email,
            email,
            EMAIL_VERIFICATION_SUBJECT,
            EMAIL_VERIFICATION_BODY.format(code=verification_code),
        )
    except SMTPError as exc:
        with suppress(RedisError):  # Delete verification code if email delivery fails
            await redis.delete(verification_key)
        logger.exception("Failed to deliver verification email")
        raise HTTPException(
            status_code=502, detail="Verification email delivery failed"
        ) from exc
