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
    field = serializers.ListField(child=serializers.CharField())
