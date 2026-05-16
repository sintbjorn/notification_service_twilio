from celery import shared_task
from django.db import transaction

from .models import DeliveryAttempt, Notification, NotificationStatus
from .services.factory import get_provider

MAX_RETRIES_PER_CHANNEL = 3
RETRY_BACKOFF_SECONDS = (5, 30, 120)


def _send_via_channel(provider, channel: str, notification: Notification) -> None:
    user = notification.user
    if channel == "email":
        provider.send(user.email, notification.subject, notification.message)
    elif channel == "sms":
        provider.send(user.phone, notification.message)
    elif channel == "telegram":
        provider.send(user.telegram_chat_id, notification.message)
    else:
        raise ValueError(f"Unknown channel: {channel}")


@shared_task(bind=True, max_retries=None)
def send_notification_task(self, notification_id: int):
    notif = (
        Notification.objects.select_related("user")
        .prefetch_related("attempts")
        .get(pk=notification_id)
    )

    if notif.status == NotificationStatus.SENT:
        return True
    if notif.status == NotificationStatus.FAILED:
        return False

    user = notif.user
    channels = user.channels()

    if notif.status == NotificationStatus.QUEUED:
        notif.status = NotificationStatus.PROCESSING
        notif.save(update_fields=["status"])

    for ch in channels:
        if notif.attempts.filter(channel=ch, success=True).exists():
            continue

        failed_attempts = notif.attempts.filter(channel=ch, success=False).count()
        if failed_attempts >= MAX_RETRIES_PER_CHANNEL:
            continue

        try:
            provider = get_provider(ch)
            _send_via_channel(provider, ch, notif)
        except Exception as exc:
            DeliveryAttempt.objects.create(
                notification=notif,
                channel=ch,
                success=False,
                error=str(exc),
            )
            next_attempt = failed_attempts + 1
            if next_attempt < MAX_RETRIES_PER_CHANNEL:
                countdown = RETRY_BACKOFF_SECONDS[
                    min(next_attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)
                ]
                raise self.retry(exc=exc, countdown=countdown) from exc
            continue

        with transaction.atomic():
            DeliveryAttempt.objects.create(notification=notif, channel=ch, success=True)
            notif.status = NotificationStatus.SENT
            notif.save(update_fields=["status"])
        return True

    notif.status = NotificationStatus.FAILED
    notif.save(update_fields=["status"])
    return False
