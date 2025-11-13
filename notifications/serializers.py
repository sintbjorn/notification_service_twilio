from rest_framework import serializers
from .models import Notification, User

class NotificationCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    subject = serializers.CharField(required=False, allow_blank=True, default="")
    message = serializers.CharField()
    idempotency_key = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def create(self, validated_data):
        from .services.producer import enqueue_notification
        user = User.objects.get(pk=validated_data["user_id"])
        return enqueue_notification(
            user=user,
            subject=validated_data.get("subject", ""),
            message=validated_data["message"],
            idempotency_key=(validated_data.get("idempotency_key") or None),
        )

class NotificationDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "user", "subject", "message", "status", "created_at")
