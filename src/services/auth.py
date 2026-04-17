from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from asyncpg import Connection
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from src.services.db import get_db

from src.models import InternalUser

security = HTTPBasic()
hasher = PasswordHasher()
dummy_password_hash = hasher.hash("invalid-password")


async def get_user(
    credentials: HTTPBasicCredentials = Depends(security),
    db: Connection = Depends(get_db),
) -> InternalUser:
    user = await db.fetchrow(
        "SELECT email, password_hash, verified FROM users WHERE email = $1",
        credentials.username,
    )
    password_hash = user["password_hash"] if user is not None else dummy_password_hash
    credentials_are_valid = False
    try:
        hasher.verify(password_hash, credentials.password)
        credentials_are_valid = user is not None
    except VerificationError:
        credentials_are_valid = False
    if not credentials_are_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return InternalUser(
        email=user["email"], password=credentials.password, verified=user["verified"]
    )
