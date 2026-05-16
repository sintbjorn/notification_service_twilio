from django.http import HttpResponse
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from .authentication import APIKeyAuthentication
from .models import Notification
from .serializers import NotificationCreateSerializer, NotificationDetailSerializer


def healthz(request):
    return HttpResponse("ok")


class NotificationViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Notification.objects.all().order_by("-id")
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "notifications"

    def get_serializer_class(self):
        if self.action == "create":
            return NotificationCreateSerializer
        return NotificationDetailSerializer
