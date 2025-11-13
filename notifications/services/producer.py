from django.db import transaction
from ..models import Notification
from ..tasks import send_notification_task

def enqueue_notification(*, user, subject: str, message: str, idempotency_key: str | None = None):
    with transaction.atomic():
        if idempotency_key:
            existed = Notification.objects.filter(idempotency_key=idempotency_key).first()
            if existed:
                return existed
        notif = Notification.objects.create(
            user=user, subject=subject, message=message, idempotency_key=idempotency_key
        )
    send_notification_task.delay(notif.id)
    return notif
