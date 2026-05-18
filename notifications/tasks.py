import logging

from celery import shared_task
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .metrics import (
    delivery_attempts_total,
    notification_outbox_publish_attempts_total,
    notifications_failed_total,
    notifications_sent_total,
)
from .models import (
    DeliveryAttempt,
    Notification,
    NotificationOutbox,
    NotificationOutboxStatus,
    NotificationStatus,
)
from .services.factory import get_provider
from .services.providers import ProviderError, ProviderResult

MAX_RETRIES_PER_CHANNEL = 3
RETRY_BACKOFF_SECONDS = (5, 30, 120)
logger = logging.getLogger(__name__)


def schedule_outbox_dispatch(outbox_id: int) -> None:
    try:
        dispatch_notification_outbox_task.delay(outbox_id=outbox_id)
    except Exception as exc:
        logger.exception(
            "notification.outbox_schedule_failed",
            extra={"outbox_id": outbox_id, "error": str(exc)},
        )


@shared_task(bind=True, max_retries=None)
def dispatch_notification_outbox_task(self, outbox_id: int | None = None, limit: int = 100):
    queryset = NotificationOutbox.objects.select_related("notification").exclude(
        status=NotificationOutboxStatus.PUBLISHED,
    )
    if outbox_id is not None:
        queryset = queryset.filter(pk=outbox_id)
    else:
        queryset = queryset.order_by("created_at")[:limit]

    published = 0
    for outbox in queryset:
        try:
            send_notification_task.delay(outbox.notification_id)
        except Exception as exc:
            notification_outbox_publish_attempts_total.labels(status="failed").inc()
            NotificationOutbox.objects.filter(pk=outbox.pk).update(
                attempts=F("attempts") + 1,
                status=NotificationOutboxStatus.FAILED,
                last_error=str(exc),
                updated_at=timezone.now(),
            )
            logger.exception(
                "notification.outbox_publish_failed",
                extra={
                    "outbox_id": outbox.id,
                    "notification_id": outbox.notification_id,
                    "error": str(exc),
                },
            )
            continue

        notification_outbox_publish_attempts_total.labels(status="published").inc()
        NotificationOutbox.objects.filter(pk=outbox.pk).update(
            attempts=F("attempts") + 1,
            status=NotificationOutboxStatus.PUBLISHED,
            last_error="",
            updated_at=timezone.now(),
            published_at=timezone.now(),
        )
        published += 1
        logger.info(
            "notification.outbox_published",
            extra={"outbox_id": outbox.id, "notification_id": outbox.notification_id},
        )

    return published


def _send_via_channel(provider, channel: str, notification: Notification) -> ProviderResult | None:
    user = notification.user
    if channel == "email":
        return provider.send(user.email, notification.subject, notification.message)
    elif channel == "sms":
        return provider.send(user.phone, notification.message)
    elif channel == "telegram":
        return provider.send(user.telegram_chat_id, notification.message)
    raise ProviderError(f"Unknown channel: {channel}", retryable=False, code="unknown_channel")


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
        logger.info(
            "notification.processing",
            extra={"notification_id": notif.id, "status": NotificationStatus.PROCESSING},
        )

    for ch in channels:
        if notif.attempts.filter(channel=ch, success=True).exists():
            continue

        failed_attempts = notif.attempts.filter(channel=ch, success=False).count()
        if failed_attempts >= MAX_RETRIES_PER_CHANNEL:
            continue

        try:
            provider = get_provider(ch)
            logger.info(
                "notification.channel_attempt",
                extra={
                    "notification_id": notif.id,
                    "channel": ch,
                    "attempt": failed_attempts + 1,
                },
            )
            provider_result = _send_via_channel(provider, ch, notif)
        except ProviderError as exc:
            original_exc = exc
            should_retry = exc.retryable
            error_message = str(exc)
        except Exception as exc:
            original_exc = exc
            should_retry = True
            error_message = str(exc)
        else:
            with transaction.atomic():
                DeliveryAttempt.objects.create(notification=notif, channel=ch, success=True)
                notif.status = NotificationStatus.SENT
                notif.save(update_fields=["status"])
            delivery_attempts_total.labels(channel=ch, status="sent").inc()
            notifications_sent_total.inc()
            logger.info(
                "notification.sent",
                extra={
                    "notification_id": notif.id,
                    "channel": ch,
                    "status": NotificationStatus.SENT,
                    "provider_message_id": (
                        provider_result.provider_message_id if provider_result else ""
                    ),
                },
            )
            return True

        DeliveryAttempt.objects.create(
            notification=notif,
            channel=ch,
            success=False,
            error=error_message,
        )
        delivery_attempts_total.labels(channel=ch, status="failed").inc()
        next_attempt = failed_attempts + 1
        logger.warning(
            "notification.channel_failed",
            extra={
                "notification_id": notif.id,
                "channel": ch,
                "attempt": next_attempt,
                "error": error_message,
                "retryable": should_retry,
            },
        )
        if should_retry and next_attempt < MAX_RETRIES_PER_CHANNEL:
            countdown = RETRY_BACKOFF_SECONDS[min(next_attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)]
            logger.info(
                "notification.retry_scheduled",
                extra={
                    "notification_id": notif.id,
                    "channel": ch,
                    "attempt": next_attempt + 1,
                    "countdown_seconds": countdown,
                },
            )
            raise self.retry(exc=original_exc, countdown=countdown) from original_exc
        continue

    notif.status = NotificationStatus.FAILED
    notif.save(update_fields=["status"])
    notifications_failed_total.inc()
    logger.error(
        "notification.failed",
        extra={"notification_id": notif.id, "status": NotificationStatus.FAILED},
    )
    return False
