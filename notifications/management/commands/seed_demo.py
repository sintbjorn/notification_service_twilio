from django.core.management.base import BaseCommand
from django.utils import timezone

from notifications.models import User
from notifications.services.producer import enqueue_notification


class Command(BaseCommand):
    help = "Create a demo user and enqueue a notification through the real delivery pipeline."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="demo@example.com")
        parser.add_argument("--phone", default="+10000000000")
        parser.add_argument("--telegram-chat-id", default="12345")
        parser.add_argument("--channel-priority", default="email,sms,telegram")
        parser.add_argument("--subject", default="Portfolio demo notification")
        parser.add_argument(
            "--message",
            default=(
                "This message was created by seed_demo and delivered through the "
                "asynchronous notification pipeline."
            ),
        )
        parser.add_argument(
            "--idempotency-key",
            default="",
            help=(
                "Optional fixed key for demonstrating idempotency. If omitted, a unique "
                "demo key is generated so each run creates a new notification."
            ),
        )

    def handle(self, *args, **options):
        email = options["email"]
        idempotency_key = options["idempotency_key"] or timezone.now().strftime(
            "demo-%Y%m%d%H%M%S%f",
        )

        user = User.objects.filter(email=email).order_by("id").first()
        user_created = user is None
        if user_created:
            user = User(email=email)
        user.phone = options["phone"]
        user.telegram_chat_id = options["telegram_chat_id"]
        user.channel_priority = options["channel_priority"]
        user.save()
        notification = enqueue_notification(
            user=user,
            subject=options["subject"],
            message=options["message"],
            idempotency_key=idempotency_key,
        )

        self.stdout.write(self.style.SUCCESS("Demo notification enqueued."))
        self.stdout.write(f"User: {user.id} ({'created' if user_created else 'updated'})")
        self.stdout.write(f"Notification: {notification.id} [{notification.status}]")
        self.stdout.write(f"Idempotency key: {notification.idempotency_key}")
        self.stdout.write("")
        self.stdout.write("Inspect:")
        self.stdout.write("- Swagger UI: http://localhost:8000/api/docs/")
        self.stdout.write("- Mailpit inbox: http://localhost:8025/")
        self.stdout.write("- Django admin: http://localhost:8000/admin/")
