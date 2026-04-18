from abc import ABC, abstractmethod

from fastapi import Request
from httpx import AsyncClient, HTTPError

from src.config import get_settings


class EmailDeliveryError(Exception):
    """Raised when the email provider fails to accept a message."""


class EmailProvider(ABC):
    """
    Abstract interface for a transactional email backend.

    Concrete implementations encapsulate vendor-specific details
    (HTTP payload shape, authentication, SMTP vs. HTTP, etc.) so the
    rest of the application only depends on this interface.
    """

    @abstractmethod
    async def send(self, to_email: str, subject: str, body: str) -> None:
        """
        Deliver a plain-text email.

        Must raise :class:`EmailDeliveryError` if the provider rejects
        the message or is unreachable.
        """

    async def aclose(self) -> None:
        """Release any underlying resources. Default no-op."""


class MailpitEmailProvider(EmailProvider):
    """
    :class:`EmailProvider` backed by an HTTP endpoint that accepts a
    Mailjet-style JSON payload on ``POST /api/v1/send``.

    Used locally with Mailpit; compatible with any Mailjet-shaped
    transactional relay. Swap this class to integrate a different
    provider (SES, SendGrid, SMTP, ...).
    """

    def __init__(self, base_url: str, from_email: str, timeout: float = 10.0):
        self._from_email = from_email
        self._client = AsyncClient(base_url=base_url, timeout=timeout)

    async def send(self, to_email: str, subject: str, body: str) -> None:
        payload = {
            "From": {"Email": self._from_email},
            "To": [{"Email": to_email}],
            "Subject": subject,
            "Text": body,
        }
        try:
            response = await self._client.post("/api/v1/send", json=payload)
            response.raise_for_status()
        except HTTPError as exc:
            raise EmailDeliveryError(
                "Email provider rejected the verification message"
            ) from exc

    async def aclose(self) -> None:
        await self._client.aclose()


async def init_email_provider() -> EmailProvider:
    settings = get_settings()
    return MailpitEmailProvider(
        base_url=str(settings.email_api_url),
        from_email=settings.email_from,
    )


def get_email_provider(request: Request) -> EmailProvider:
    return request.app.state.email_provider
