from django.db import transaction
from django.db.utils import IntegrityError

from ..models import Notification
from ..tasks import send_notification_task


def enqueue_notification(*, user, subject: str, message: str, idempotency_key: str | None = None):
    created = False

    try:
        with transaction.atomic():
            if idempotency_key:
                notif, created = Notification.objects.get_or_create(
                    idempotency_key=idempotency_key,
                    defaults={"user": user, "subject": subject, "message": message},
                )
            else:
                notif = Notification.objects.create(user=user, subject=subject, message=message)
                created = True

            if created:
                transaction.on_commit(lambda: send_notification_task.delay(notif.id))
    except IntegrityError:
        if not idempotency_key:
            raise
        notif = Notification.objects.get(idempotency_key=idempotency_key)

    return notif
