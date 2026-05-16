import logging

from django.db import transaction
from django.db.utils import IntegrityError

from ..models import Notification
from ..tasks import send_notification_task

logger = logging.getLogger(__name__)


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
                logger.info(
                    "notification.created",
                    extra={
                        "notification_id": notif.id,
                        "user_id": user.id,
                        "idempotency_key": idempotency_key,
                    },
                )
                transaction.on_commit(lambda: send_notification_task.delay(notif.id))
    except IntegrityError:
        if not idempotency_key:
            raise
        notif = Notification.objects.get(idempotency_key=idempotency_key)
        logger.info(
            "notification.idempotency_conflict",
            extra={"notification_id": notif.id, "idempotency_key": idempotency_key},
        )

    if idempotency_key and not created:
        logger.info(
            "notification.idempotency_reused",
            extra={"notification_id": notif.id, "idempotency_key": idempotency_key},
        )

    return notif
