from anyio import to_thread
from argon2 import PasswordHasher
from asyncpg import Connection, UniqueViolationError
from fastapi import APIRouter, Depends, HTTPException

from app.constants import EMAIL_VERIFICATION_BODY, EMAIL_VERIFICATION_SUBJECT
from app.utils import send_email

from .db import get_db
from .models import User

router = APIRouter()
hasher = PasswordHasher()


@router.post("/users")
async def create_user(user: User, db: Connection = Depends(get_db)):
    password_hash = await to_thread.run_sync(
        hasher.hash, user.password.get_secret_value()
    )
    try:
        async with db.transaction():
            await db.execute(
                "INSERT INTO users (email, password_hash) VALUES ($1, $2)",
                user.email,
                password_hash,
            )
    except UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc
    await to_thread.run_sync(
        send_email,
        user.email,
        EMAIL_VERIFICATION_SUBJECT,
        EMAIL_VERIFICATION_BODY.format(code=1234),
    )
