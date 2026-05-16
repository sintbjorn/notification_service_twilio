from django.http import HttpResponse
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
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
