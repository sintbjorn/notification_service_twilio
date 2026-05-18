from django.db import models
from django.utils import timezone


class NotificationStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    PROCESSING = "processing", "Processing"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"


class NotificationOutboxStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PUBLISHED = "published", "Published"
    FAILED = "failed", "Failed"


class User(models.Model):
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True, null=True)
    telegram_chat_id = models.CharField(max_length=64, blank=True, null=True)
    # Channel priority string, e.g. "email,sms,telegram"
    channel_priority = models.CharField(max_length=128, default="email,sms,telegram")

    def __str__(self):
        return self.email or self.phone or self.telegram_chat_id or f"User#{self.pk}"

    def channels(self):
        return [c.strip() for c in self.channel_priority.split(",") if c.strip()]


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.CharField(max_length=200, blank=True, default="")
    message = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=16,
        choices=NotificationStatus.choices,
        default=NotificationStatus.QUEUED,
    )
    idempotency_key = models.CharField(max_length=64, blank=True, null=True, unique=True)

    def __str__(self):
        return f"Notification#{self.pk} -> {self.user}"


class NotificationOutbox(models.Model):
    notification = models.OneToOneField(
        Notification,
        on_delete=models.CASCADE,
        related_name="outbox",
    )
    status = models.CharField(
        max_length=16,
        choices=NotificationOutboxStatus.choices,
        default=NotificationOutboxStatus.PENDING,
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"], name="notif_outbox_status_idx"),
        ]

    def __str__(self):
        return f"Outbox#{self.pk} -> Notification#{self.notification_id} [{self.status}]"


class DeliveryAttempt(models.Model):
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    channel = models.CharField(max_length=32)  # email/sms/telegram
    success = models.BooleanField(default=False)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(
                fields=["notification", "channel", "-created_at"],
                name="notificatio_notific_66e0c2_idx",
            )
        ]
