from django.contrib import admin
from django.db.models import Count, Max, Q
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode

from .models import DeliveryAttempt, Notification, NotificationStatus, User
from .tasks import send_notification_task


STATUS_COLORS = {
    NotificationStatus.QUEUED: "#6b7280",
    NotificationStatus.PROCESSING: "#2563eb",
    NotificationStatus.SENT: "#15803d",
    NotificationStatus.FAILED: "#b91c1c",
}


def admin_link(url_name: str, object_id: int, label: str):
    url = reverse(url_name, args=[object_id])
    return format_html('<a href="{}">{}</a>', url, label)


def changelist_link(url_name: str, query: dict[str, str], label: str):
    url = f"{reverse(url_name)}?{urlencode(query)}"
    return format_html('<a href="{}">{}</a>', url, label)


class DeliveryAttemptInline(admin.TabularInline):
    model = DeliveryAttempt
    extra = 0
    can_delete = False
    fields = ("created_at", "channel", "success_badge", "error_preview")
    readonly_fields = fields
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Result")
    def success_badge(self, obj):
        color = "#15803d" if obj.success else "#b91c1c"
        label = "sent" if obj.success else "failed"
        return format_html('<strong style="color: {};">{}</strong>', color, label)

    @admin.display(description="Error")
    def error_preview(self, obj):
        if not obj.error:
            return "-"
        if len(obj.error) <= 120:
            return obj.error
        return f"{obj.error[:117]}..."


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "email",
        "phone",
        "telegram_chat_id",
        "channel_priority",
        "notifications_count",
        "latest_notification_at",
    )
    search_fields = ("id", "email", "phone", "telegram_chat_id")
    list_filter = ("channel_priority",)
    ordering = ("-id",)
    list_per_page = 50

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            latest_notification=Max("notification__created_at"),
            notifications_total=Count("notification"),
        )

    @admin.display(description="Notifications", ordering="notifications_total")
    def notifications_count(self, obj):
        if not obj.notifications_total:
            return 0
        return changelist_link(
            "admin:notifications_notification_changelist",
            {"user__id__exact": str(obj.id)},
            str(obj.notifications_total),
        )

    @admin.display(description="Latest notification", ordering="latest_notification")
    def latest_notification_at(self, obj):
        return obj.latest_notification or "-"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user_link",
        "subject",
        "status_badge",
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
    readonly_fields = ("created_at", "attempts_count", "failed_attempts_count")
    autocomplete_fields = ("user",)
    date_hierarchy = "created_at"
    ordering = ("-created_at", "-id")
    inlines = (DeliveryAttemptInline,)
    actions = ("clone_failed_notifications",)
    list_select_related = ("user",)
    list_per_page = 50
    fieldsets = (
        ("Delivery", {"fields": ("user", "subject", "message")}),
        ("State", {"fields": ("status", "created_at")}),
        ("Idempotency", {"fields": ("idempotency_key",)}),
        ("Attempt summary", {"fields": ("attempts_count", "failed_attempts_count")}),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("user")
        return queryset.annotate(
            attempts_total=Count("attempts"),
            failed_attempts_total=Count("attempts", filter=Q(attempts__success=False)),
        )

    @admin.display(description="Attempts", ordering="attempts_total")
    def attempts_count(self, obj):
        if obj is None:
            return 0
        count = getattr(obj, "attempts_total", obj.attempts.count())
        if not count:
            return 0
        return changelist_link(
            "admin:notifications_deliveryattempt_changelist",
            {"notification__id__exact": str(obj.id)},
            str(count),
        )

    @admin.display(description="Failed", ordering="failed_attempts_total")
    def failed_attempts_count(self, obj):
        if obj is None:
            return 0
        return getattr(obj, "failed_attempts_total", obj.attempts.filter(success=False).count())

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        color = STATUS_COLORS.get(obj.status, "#6b7280")
        return format_html('<strong style="color: {};">{}</strong>', color, obj.status)

    @admin.display(description="User", ordering="user")
    def user_link(self, obj):
        return admin_link("admin:notifications_user_change", obj.user_id, str(obj.user))

    @admin.action(description="Clone selected failed notifications for redelivery")
    def clone_failed_notifications(self, request, queryset):
        failed_notifications = queryset.filter(status=NotificationStatus.FAILED)
        cloned = 0

        for notification in failed_notifications:
            clone = Notification.objects.create(
                user=notification.user,
                subject=notification.subject,
                message=notification.message,
            )
            send_notification_task.delay(clone.id)
            cloned += 1

        self.message_user(request, f"Cloned {cloned} failed notification(s) for redelivery.")


@admin.register(DeliveryAttempt)
class DeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "notification_link",
        "user_link",
        "channel",
        "success_badge",
        "created_at",
        "error_preview",
    )
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
    list_select_related = ("notification__user",)
    list_per_page = 50

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("notification__user")

    @admin.display(description="User")
    def user_link(self, obj):
        return admin_link(
            "admin:notifications_user_change",
            obj.notification.user_id,
            str(obj.notification.user),
        )

    @admin.display(description="Notification", ordering="notification")
    def notification_link(self, obj):
        return admin_link(
            "admin:notifications_notification_change",
            obj.notification_id,
            f"Notification #{obj.notification_id}",
        )

    @admin.display(description="Result", ordering="success")
    def success_badge(self, obj):
        color = "#15803d" if obj.success else "#b91c1c"
        label = "sent" if obj.success else "failed"
        return format_html('<strong style="color: {};">{}</strong>', color, label)

    @admin.display(description="Error")
    def error_preview(self, obj):
        if not obj.error:
            return "-"
        if len(obj.error) <= 80:
            return obj.error
        return f"{obj.error[:77]}..."

    def has_add_permission(self, request):
        return False
