from functools import lru_cache

from pydantic import EmailStr, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_url: PostgresDsn
    redis_url: RedisDsn
    verification_code_ttl_seconds: int = 60
    api_log_level: str = "INFO"
    api_log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    smtp_host: str
    smtp_port: int
    smtp_from_email: EmailStr = "no-reply@example.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
