from django.contrib import admin
from django.db.models import Count, Q

from .models import DeliveryAttempt, Notification, User


class DeliveryAttemptInline(admin.TabularInline):
    model = DeliveryAttempt
    extra = 0
    can_delete = False
    fields = ("created_at", "channel", "success", "error")
    readonly_fields = fields
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email",
        "phone",
        "telegram_chat_id",
        "channel_priority",
        "notifications_count",
    )
    search_fields = ("id", "email", "phone", "telegram_chat_id")
    list_filter = ("channel_priority",)
    ordering = ("-id",)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(notifications_total=Count("notification"))

    @admin.display(description="Notifications", ordering="notifications_total")
    def notifications_count(self, obj):
        return obj.notifications_total


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "subject",
        "status",
        "attempts_count",
        "failed_attempts_count",
        "created_at",
        "idempotency_key",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "id",
        "subject",
        "message",
        "idempotency_key",
        "user__email",
        "user__phone",
        "user__telegram_chat_id",
    )
    readonly_fields = ("created_at",)
    autocomplete_fields = ("user",)
    date_hierarchy = "created_at"
    ordering = ("-created_at", "-id")
    inlines = (DeliveryAttemptInline,)

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("user")
        return queryset.annotate(
            attempts_total=Count("attempts"),
            failed_attempts_total=Count("attempts", filter=Q(attempts__success=False)),
        )

    @admin.display(description="Attempts", ordering="attempts_total")
    def attempts_count(self, obj):
        return obj.attempts_total

    @admin.display(description="Failed", ordering="failed_attempts_total")
    def failed_attempts_count(self, obj):
        return obj.failed_attempts_total


@admin.register(DeliveryAttempt)
class DeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "notification", "user", "channel", "success", "created_at")
    list_filter = ("channel", "success", "created_at")
    search_fields = (
        "id",
        "notification__id",
        "notification__subject",
        "notification__idempotency_key",
        "notification__user__email",
        "notification__user__phone",
        "error",
    )
    readonly_fields = ("notification", "channel", "success", "error", "created_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at", "-id")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("notification__user")

    @admin.display(description="User")
    def user(self, obj):
        return obj.notification.user

    def has_add_permission(self, request):
        return False
