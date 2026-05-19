import smtplib
from contextlib import suppress
from email.message import EmailMessage

from .base import ProviderError, ProviderResult


class EmailProvider:
    channel = "email"

    def __init__(self, host, port, user, password, use_tls=True, sender=None):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_tls = use_tls
        self.sender = sender or user or "no-reply@example.com"

    def send(self, to_email: str, subject: str, body: str) -> ProviderResult:
        if not to_email:
            raise ProviderError("Recipient email is empty", retryable=False, code="missing_email")

        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = to_email
        msg["Subject"] = subject or "(no subject)"
        msg.set_content(body)

        try:
            with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                if self.use_tls:
                    with suppress(smtplib.SMTPException):
                        smtp.starttls()
                if self.user and self.password:
                    smtp.login(self.user, self.password)
                smtp.send_message(msg)
        except smtplib.SMTPRecipientsRefused as exc:
            raise ProviderError(
                f"Email recipient refused: {to_email}",
                retryable=False,
                code="recipient_refused",
            ) from exc
        except smtplib.SMTPException as exc:
            raise ProviderError(f"SMTP error: {exc}", retryable=True, code="smtp_error") from exc
        except OSError as exc:
            raise ProviderError(
                f"SMTP connection error: {exc}",
                retryable=True,
                code="smtp_connection_error",
            ) from exc

        return ProviderResult(channel=self.channel)
