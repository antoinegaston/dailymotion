from typing import Callable

from fastapi import HTTPException, Request
from limits import parse
from limits.strategies import MovingWindowRateLimiter

from src.logging import get_logger

logger = get_logger(__name__)


def limit_rate(rate: str) -> Callable:
    async def inner(request: Request):
        limiter: MovingWindowRateLimiter = request.app.state.limiter
        client_host = request.client.host if request.client else "unknown"
        if not limiter.hit(parse(rate), request.url.path, client_host):
            logger.warning("Rate limit exceeded for request path=%s", request.url.path)
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return inner
