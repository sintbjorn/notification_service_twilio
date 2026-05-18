from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

from .models import NotificationOutbox, NotificationOutboxStatus

notifications_sent_total = Counter(
    "notifications_sent_total",
    "Total notifications delivered successfully.",
)
notifications_failed_total = Counter(
    "notifications_failed_total",
    "Total notifications that exhausted all delivery channels.",
)
delivery_attempts_total = Counter(
    "delivery_attempts_total",
    "Total delivery attempts by channel and status.",
    ["channel", "status"],
)
notification_outbox_publish_attempts_total = Counter(
    "notification_outbox_publish_attempts_total",
    "Total attempts to publish notification outbox rows to the Celery broker.",
    ["status"],
)
notification_outbox_rows_total = Gauge(
    "notification_outbox_rows_total",
    "Current number of notification outbox rows by status.",
    ["status"],
)
notification_outbox_oldest_pending_age_seconds = Gauge(
    "notification_outbox_oldest_pending_age_seconds",
    "Age in seconds of the oldest pending or failed notification outbox row.",
)


def update_outbox_metrics() -> None:
    for status in NotificationOutboxStatus.values:
        notification_outbox_rows_total.labels(status=status).set(
            NotificationOutbox.objects.filter(status=status).count(),
        )

    oldest_waiting = (
        NotificationOutbox.objects.filter(
            status__in=[
                NotificationOutboxStatus.PENDING,
                NotificationOutboxStatus.FAILED,
            ],
        )
        .order_by("created_at")
        .first()
    )
    if oldest_waiting is None:
        notification_outbox_oldest_pending_age_seconds.set(0)
        return
    notification_outbox_oldest_pending_age_seconds.set(
        max((timezone.now() - oldest_waiting.created_at).total_seconds(), 0),
    )


def metrics_view(request):
    expected_key = getattr(settings, "METRICS_API_KEY", "") or getattr(
        settings,
        "NOTIFICATION_API_KEY",
        "",
    )
    provided_key = request.headers.get("X-API-Key", "")

    if expected_key and provided_key != expected_key:
        return HttpResponse("Unauthorized", status=401)

    update_outbox_metrics()
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)


metrics_view = extend_schema(exclude=True)(metrics_view)
