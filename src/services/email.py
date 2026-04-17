import smtplib
from email.message import EmailMessage

from src.config import get_settings

SMTPError = (smtplib.SMTPException, OSError)


def send_email(to_email: str, subject: str, body: str) -> None:
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(
        host=settings.smtp_host, port=settings.smtp_port, timeout=10
    ) as smtp:
        smtp.send_message(message)
