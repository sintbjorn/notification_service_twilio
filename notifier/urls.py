from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from notifications.views import NotificationViewSet, healthz
from notifications import graphql_urls

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("graphql", include(graphql_urls.urlpatterns)),
    path("healthz", healthz),
]
