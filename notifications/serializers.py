from rest_framework import serializers

from .models import Notification, User


class NotificationCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(help_text="Target user id.")
    subject = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional notification subject.",
    )
    message = serializers.CharField(help_text="Notification body.")
    idempotency_key = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Optional client-generated key used to prevent duplicate enqueueing.",
    )

    def validate_user_id(self, value):
        if not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError("User does not exist.")
        return value

    def create(self, validated_data):
        from .services.producer import enqueue_notification

        user = User.objects.get(pk=validated_data["user_id"])
        return enqueue_notification(
            user=user,
            subject=validated_data.get("subject", ""),
            message=validated_data["message"],
            idempotency_key=(validated_data.get("idempotency_key") or None),
        )

    def to_representation(self, instance):
        return NotificationDetailSerializer(instance).data


class NotificationDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "user", "subject", "message", "status", "created_at")


class ErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class ValidationErrorSerializer(serializers.Serializer):
    user_id = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Validation errors for the target user id.",
    )
    subject = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Validation errors for the optional notification subject.",
    )
    message = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Validation errors for the notification body.",
    )
    idempotency_key = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Validation errors for the client idempotency key.",
    )
    non_field_errors = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Validation errors that are not tied to a single request field.",
    )


class HealthLiveSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok"])


class HealthReadyChecksSerializer(serializers.Serializer):
    database = serializers.BooleanField()
    cache = serializers.BooleanField()


class HealthReadySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "error"])
    checks = HealthReadyChecksSerializer()
