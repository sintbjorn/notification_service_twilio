from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from notifications import graphql_urls
from notifications.health import health_live, health_ready
from notifications.metrics import metrics_view
from notifications.telegram import telegram_webhook
from notifications.views import NotificationViewSet

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="swagger-ui", permanent=False), name="root"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui-alias",
    ),
    path("api/", include(router.urls)),
    path("metrics", metrics_view, name="metrics"),
    path("webhooks/telegram/", telegram_webhook, name="telegram-webhook"),
    path("graphql", graphql_urls.graphql_view, name="graphql"),
    path("graphql/", graphql_urls.graphql_view, name="graphql-slash"),
    path("healthz", health_live),
    path("health/live", health_live, name="health-live"),
    path("health/ready", health_ready, name="health-ready"),
]
