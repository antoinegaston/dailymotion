from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, SecretStr


class User(BaseModel):
    email: EmailStr
    password: Annotated[SecretStr, Field(min_length=8, max_length=128)]
