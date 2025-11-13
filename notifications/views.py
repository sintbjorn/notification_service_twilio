from rest_framework import viewsets, mixins, status
from rest_framework.response import Response
from django.http import HttpResponse
from .serializers import NotificationCreateSerializer, NotificationDetailSerializer
from .models import Notification

def healthz(request):
    return HttpResponse("ok")

class NotificationViewSet(mixins.CreateModelMixin,
                           mixins.RetrieveModelMixin,
                           viewsets.GenericViewSet):
    queryset = Notification.objects.all().order_by("-id")

    def get_serializer_class(self):
        return NotificationCreateSerializer if self.action == "create" else NotificationDetailSerializer
