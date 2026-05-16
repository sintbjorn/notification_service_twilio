from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from notifications import graphql_urls
from notifications.metrics import metrics_view
from notifications.telegram import telegram_webhook
from notifications.views import NotificationViewSet, healthz

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/", include(router.urls)),
    path("metrics", metrics_view, name="metrics"),
    path("webhooks/telegram/", telegram_webhook, name="telegram-webhook"),
    path("graphql", include(graphql_urls.urlpatterns)),
    path("healthz", healthz),
]
