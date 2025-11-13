import os
from .providers import EmailProvider, SmsProvider, TelegramProvider

def get_provider(channel: str):
    if channel == "email":
        return EmailProvider(
            host=os.getenv("SMTP_HOST", "mailhog"),
            port=int(os.getenv("SMTP_PORT", "1025")),
            user=os.getenv("SMTP_USER", ""),
            password=os.getenv("SMTP_PASSWORD", ""),
            use_tls=False,
            sender=os.getenv("SMTP_SENDER", "no-reply@example.com"),
        )
    if channel == "sms":
        return SmsProvider(
            os.getenv("TWILIO_SID", "sid"),
            os.getenv("TWILIO_TOKEN", "token"),
            os.getenv("TWILIO_FROM", "+10000000000"),
        )
    if channel == "telegram":
        return TelegramProvider(os.getenv("TELEGRAM_BOT_TOKEN", "test-token"))
    raise ValueError(f"Unknown channel: {channel}")
