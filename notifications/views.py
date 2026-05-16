from django.http import HttpResponse
from rest_framework import mixins, viewsets

from .models import Notification
from .serializers import NotificationCreateSerializer, NotificationDetailSerializer


def healthz(request):
    return HttpResponse("ok")


class NotificationViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Notification.objects.all().order_by("-id")

    def get_serializer_class(self):
        if self.action == "create":
            return NotificationCreateSerializer
        return NotificationDetailSerializer
