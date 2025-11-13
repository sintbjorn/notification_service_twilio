from celery import shared_task
from django.db import transaction
from .models import Notification, DeliveryAttempt
from .services.factory import get_provider

MAX_RETRIES_PER_CHANNEL = 3

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def send_notification_task(self, notification_id: int):
    notif = Notification.objects.select_related("user").get(pk=notification_id)
    user = notif.user
    channels = user.channels()

    for ch in channels:
        if notif.attempts.filter(channel=ch, success=True).exists():
            continue

        provider = get_provider(ch)

        for attempt_num in range(1, MAX_RETRIES_PER_CHANNEL + 1):
            try:
                if ch == "email":
                    provider.send(user.email, notif.subject, notif.message)
                elif ch == "sms":
                    provider.send(user.phone, notif.message)
                elif ch == "telegram":
                    provider.send(user.telegram_chat_id, notif.message)
                with transaction.atomic():
                    DeliveryAttempt.objects.create(notification=notif, channel=ch, success=True)
                    notif.status = "sent"
                    notif.save(update_fields=["status"])
                return True
            except Exception as e:
                DeliveryAttempt.objects.create(notification=notif, channel=ch, success=False, error=str(e))
                if attempt_num < MAX_RETRIES_PER_CHANNEL:
                    raise

    notif.status = "failed"
    notif.save(update_fields=["status"])
    return False
