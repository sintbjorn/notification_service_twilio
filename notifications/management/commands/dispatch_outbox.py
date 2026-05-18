from django.core.management.base import BaseCommand

from notifications.tasks import dispatch_notification_outbox_task


class Command(BaseCommand):
    help = "Publish pending notification outbox rows to Celery."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--outbox-id", type=int, default=None)

    def handle(self, *args, **options):
        published = dispatch_notification_outbox_task(
            outbox_id=options["outbox_id"],
            limit=options["limit"],
        )
        self.stdout.write(self.style.SUCCESS(f"Published {published} outbox row(s)."))
