from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

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


def metrics_view(request):
    expected_key = getattr(settings, "METRICS_API_KEY", "") or getattr(
        settings,
        "NOTIFICATION_API_KEY",
        "",
    )
    provided_key = request.headers.get("X-API-Key", "")

    if expected_key and provided_key != expected_key:
        return HttpResponse("Unauthorized", status=401)

    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)


metrics_view = extend_schema(exclude=True)(metrics_view)
