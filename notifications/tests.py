import json
from unittest.mock import Mock, patch

from celery.exceptions import Retry
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

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


class NotificationAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create(email="user@example.com")

    def test_create_notification_requires_api_key(self):
        response = self.client.post(
            "/api/notifications/",
            {"user_id": self.user.id, "message": "Hello"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_create_notification_rejects_invalid_api_key(self):
        response = self.client.post(
            "/api/notifications/",
            {"user_id": self.user.id, "message": "Hello"},
            format="json",
            HTTP_X_API_KEY="wrong-key",
        )

        self.assertEqual(response.status_code, 401)

    def test_create_notification_accepts_valid_api_key(self):
        with patch("notifications.services.producer.send_notification_task.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    "/api/notifications/",
                    {"user_id": self.user.id, "message": "Hello"},
                    format="json",
                    HTTP_X_API_KEY="test-notification-api-key",
                )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Notification.objects.count(), 1)
        delay.assert_called_once_with(Notification.objects.get().id)

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
            "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
            "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
            "DEFAULT_THROTTLE_RATES": {"notifications": "1/min"},
        },
    )
    def test_notification_endpoint_is_throttled(self):
        cache.clear()

        with patch("notifications.services.producer.send_notification_task.delay"):
            first = self.client.post(
                "/api/notifications/",
                {"user_id": self.user.id, "message": "First"},
                format="json",
                HTTP_X_API_KEY="test-notification-api-key",
            )
            second = self.client.post(
                "/api/notifications/",
                {"user_id": self.user.id, "message": "Second"},
                format="json",
                HTTP_X_API_KEY="test-notification-api-key",
            )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 429)


class RequestIDMiddlewareTests(TestCase):
    def test_response_includes_provided_request_id(self):
        response = self.client.get("/healthz", HTTP_X_REQUEST_ID="portfolio-request-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Request-ID"], "portfolio-request-1")

    def test_response_includes_generated_request_id(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["X-Request-ID"])


class TelegramWebhookTests(TestCase):
    def telegram_update(self, chat_id="12345", text="/start"):
        return {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "chat": {"id": chat_id, "type": "private"},
                "text": text,
            },
        }

    @override_settings(TELEGRAM_WEBHOOK_SECRET="")
    def test_start_creates_user_with_telegram_chat_id(self):
        response = self.client.post(
            "/api/telegram/webhook/",
            json.dumps(self.telegram_update()),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)
        user = User.objects.get()
        self.assertEqual(user.telegram_chat_id, "12345")
        self.assertEqual(user.channel_priority, "telegram,email,sms")

    @override_settings(TELEGRAM_WEBHOOK_SECRET="")
    def test_start_reuses_existing_telegram_user(self):
        User.objects.create(telegram_chat_id="12345")

        response = self.client.post(
            "/api/telegram/webhook/",
            json.dumps(self.telegram_update()),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    @override_settings(TELEGRAM_WEBHOOK_SECRET="expected-secret")
    def test_rejects_invalid_telegram_secret(self):
        response = self.client.post(
            "/api/telegram/webhook/",
            json.dumps(self.telegram_update()),
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong-secret",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(User.objects.count(), 0)

    @override_settings(TELEGRAM_WEBHOOK_SECRET="")
    def test_ignores_non_start_messages(self):
        response = self.client.post(
            "/api/telegram/webhook/",
            json.dumps(self.telegram_update(text="hello")),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)
