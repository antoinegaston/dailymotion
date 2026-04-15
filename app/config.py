from functools import lru_cache

from pydantic import EmailStr, PostgresDsn
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_url: PostgresDsn
    api_log_level: str
    api_log_format: str
    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_from_email: EmailStr = "no-reply@example.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
