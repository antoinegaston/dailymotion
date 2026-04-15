from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, SecretStr


class User(BaseModel):
    email: EmailStr
    password: Annotated[SecretStr, Field(min_length=8, max_length=128)]


class OutboundEmail(BaseModel):
    to_email: EmailStr
    subject: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1, max_length=5000)]
