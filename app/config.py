from functools import lru_cache

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_url: PostgresDsn
    api_log_level: str
    api_log_format: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
