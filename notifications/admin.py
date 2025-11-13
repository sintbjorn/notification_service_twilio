from django.contrib import admin
from .models import User, Notification, DeliveryAttempt

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "phone", "telegram_chat_id", "channel_priority")

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "subject", "status", "created_at", "idempotency_key")
    list_filter = ("status",)

@admin.register(DeliveryAttempt)
class DeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "notification", "channel", "success", "created_at")
    list_filter = ("channel", "success")
