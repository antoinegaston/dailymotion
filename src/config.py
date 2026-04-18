from functools import lru_cache
from typing import Literal

from pydantic import EmailStr, HttpUrl, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_url: PostgresDsn
    redis_url: RedisDsn
    verification_code_ttl_seconds: int = 60
    api_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    email_api_url: HttpUrl
    email_from: EmailStr = "no-reply@example.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
