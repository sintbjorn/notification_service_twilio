from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from .authentication import APIKeyAuthentication
from .models import Notification
from .serializers import (
    ErrorSerializer,
    NotificationCreateSerializer,
    NotificationDetailSerializer,
    ValidationErrorSerializer,
)


@extend_schema_view(
    create=extend_schema(
        summary="Create notification",
        tags=["Notifications"],
        description=(
            "Creates a durable notification and enqueues asynchronous delivery after the "
            "database transaction commits. Reusing the same `idempotency_key` returns the "
            "existing notification instead of enqueueing a duplicate."
        ),
        request=NotificationCreateSerializer,
        responses={
            201: OpenApiResponse(NotificationDetailSerializer, description="Notification queued."),
            400: OpenApiResponse(ValidationErrorSerializer, description="Validation error."),
            401: OpenApiResponse(ErrorSerializer, description="Missing or invalid API key."),
            429: OpenApiResponse(ErrorSerializer, description="Notification rate limit exceeded."),
        },
        examples=[
            OpenApiExample(
                "Create notification",
                value={
                    "user_id": 1,
                    "subject": "Renovation update",
                    "message": "Your inspection report is ready.",
                    "idempotency_key": "notification-2026-0001",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Queued response",
                value={
                    "id": 42,
                    "user": 1,
                    "subject": "Renovation update",
                    "message": "Your inspection report is ready.",
                    "status": "queued",
                    "created_at": "2026-05-16T12:00:00Z",
                },
                response_only=True,
                status_codes=["201"],
            ),
            OpenApiExample(
                "Validation error",
                value={"user_id": ["User does not exist."]},
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "Unauthorized",
                value={"detail": "Authentication credentials were not provided."},
                response_only=True,
                status_codes=["401"],
            ),
            OpenApiExample(
                "Rate limited",
                value={"detail": "Request was throttled. Expected available in 42 seconds."},
                response_only=True,
                status_codes=["429"],
            ),
        ],
    ),
    retrieve=extend_schema(
        summary="Retrieve notification status",
        tags=["Notifications"],
        description="Returns the current notification status and delivery payload metadata.",
        responses={
            200: NotificationDetailSerializer,
            401: OpenApiResponse(ErrorSerializer, description="Missing or invalid API key."),
            404: OpenApiResponse(ErrorSerializer, description="Notification was not found."),
        },
        examples=[
            OpenApiExample(
                "Not found",
                value={"detail": "Not found."},
                response_only=True,
                status_codes=["404"],
            )
        ],
    ),
)
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
