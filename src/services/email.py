from fastapi import Request
from httpx import AsyncClient, HTTPError

from src.config import get_settings


class EmailDeliveryError(Exception):
    """Raised when the third-party email provider fails to accept a message."""


async def init_email_client() -> AsyncClient:
    settings = get_settings()
    return AsyncClient(base_url=str(settings.email_api_url), timeout=10.0)


def get_email_client(request: Request) -> AsyncClient:
    return request.app.state.email_client


async def send_email(
    client: AsyncClient, to_email: str, subject: str, body: str
) -> None:
    settings = get_settings()
    payload = {
        "From": {"Email": settings.email_from},
        "To": [{"Email": to_email}],
        "Subject": subject,
        "Text": body,
    }
    try:
        response = await client.post("/api/v1/send", json=payload)
        response.raise_for_status()
    except HTTPError as exc:
        raise EmailDeliveryError(
            "Email provider rejected the verification message"
        ) from exc
