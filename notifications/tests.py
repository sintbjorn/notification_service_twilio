from unittest.mock import Mock, patch

from celery.exceptions import Retry
from django.test import TestCase

from notifications.models import DeliveryAttempt, Notification, NotificationStatus, User
from notifications.services.producer import enqueue_notification
from notifications.tasks import send_notification_task


class NotificationDeliveryTests(TestCase):
    def test_retries_current_channel_then_falls_back_to_next_channel(self):
        user = User.objects.create(
            email="user@example.com",
            phone="+15551234567",
            channel_priority="email,sms",
        )
        notification = Notification.objects.create(user=user, subject="Hello", message="Body")
        email_provider = Mock()
        email_provider.send.side_effect = RuntimeError("smtp unavailable")
        sms_provider = Mock()

        with patch(
            "notifications.tasks.get_provider",
            side_effect=lambda channel: {"email": email_provider, "sms": sms_provider}[channel],
        ):
            with self.assertRaises(Retry):
                send_notification_task(notification.id)
            with self.assertRaises(Retry):
                send_notification_task(notification.id)

            self.assertTrue(send_notification_task(notification.id))

        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationStatus.SENT)
        self.assertEqual(
            DeliveryAttempt.objects.filter(
                notification=notification,
                channel="email",
                success=False,
            ).count(),
            3,
        )
        self.assertEqual(
            DeliveryAttempt.objects.filter(
                notification=notification,
                channel="sms",
                success=True,
            ).count(),
            1,
        )

    def test_marks_notification_failed_after_all_channel_attempts_fail(self):
        user = User.objects.create(email="user@example.com", channel_priority="email")
        notification = Notification.objects.create(user=user, subject="Hello", message="Body")
        email_provider = Mock()
        email_provider.send.side_effect = RuntimeError("smtp unavailable")

        with patch("notifications.tasks.get_provider", return_value=email_provider):
            with self.assertRaises(Retry):
                send_notification_task(notification.id)
            with self.assertRaises(Retry):
                send_notification_task(notification.id)

            self.assertFalse(send_notification_task(notification.id))

        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationStatus.FAILED)
        self.assertEqual(
            DeliveryAttempt.objects.filter(notification=notification, success=False).count(),
            3,
        )


class EnqueueNotificationTests(TestCase):
    def test_idempotency_key_returns_existing_notification_without_requeueing(self):
        user = User.objects.create(email="user@example.com")

        with patch("notifications.services.producer.send_notification_task.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                first = enqueue_notification(
                    user=user,
                    subject="Hello",
                    message="First",
                    idempotency_key="same-key",
                )
            second = enqueue_notification(
                user=user,
                subject="Hello again",
                message="Second",
                idempotency_key="same-key",
            )

        self.assertEqual(first.id, second.id)
        self.assertEqual(Notification.objects.count(), 1)
        delay.assert_called_once_with(first.id)
