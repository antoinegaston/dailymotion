import logging
import logging.config
from functools import lru_cache

from src.config import get_settings


@lru_cache
def configure_logging() -> None:

    settings = get_settings()
    level = settings.api_log_level

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": settings.api_log_format,
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {"handlers": ["console"], "level": "WARNING"},
            "loggers": {
                "src": {
                    "handlers": ["console"],
                    "level": level,
                    "propagate": False,
                }
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
