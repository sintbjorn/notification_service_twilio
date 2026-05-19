import json
from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, Mock, patch

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from notifications.models import (
    DeliveryAttempt,
    Notification,
    NotificationOutbox,
    NotificationOutboxStatus,
    NotificationStatus,
    User,
)
from notifications.services.producer import enqueue_notification
from notifications.services.providers import (
    EmailProvider,
    ProviderError,
    SmsProvider,
    TelegramProvider,
)
from notifications.tasks import dispatch_notification_outbox_task, send_notification_task


class ProviderContractTests(SimpleTestCase):
    def twilio_response(self, *, ok=True, status_code=201, payload=None, text=""):
        response = Mock()
        response.ok = ok
        response.status_code = status_code
        response.text = text
        response.json.return_value = payload or {}
        return response

    def telegram_response(self, *, ok=True, status_code=200, payload=None, text=""):
        response = Mock()
        response.ok = ok
        response.status_code = status_code
        response.text = text
        response.json.return_value = payload or {}
        return response

    def assert_provider_error(self, error, *, retryable, code):
        self.assertEqual(error.retryable, retryable)
        self.assertEqual(error.code, code)

    def test_email_provider_sends_smtp_message(self):
        smtp_client = Mock()
        smtp_context = MagicMock()
        smtp_context.__enter__.return_value = smtp_client
        smtp_context.__exit__.return_value = None

        provider = EmailProvider(
            host="smtp.example.com",
            port=587,
            user="smtp-user",
            password="smtp-password",
            use_tls=True,
            sender="no-reply@example.com",
        )

        with patch(
            "notifications.services.providers.email.smtplib.SMTP",
            return_value=smtp_context,
        ):
            result = provider.send("user@example.com", "Subject", "Body")

        self.assertEqual(result.channel, "email")
        smtp_client.starttls.assert_called_once()
        smtp_client.login.assert_called_once_with("smtp-user", "smtp-password")
        sent_message = smtp_client.send_message.call_args.args[0]
        self.assertEqual(sent_message["From"], "no-reply@example.com")
        self.assertEqual(sent_message["To"], "user@example.com")
        self.assertEqual(sent_message["Subject"], "Subject")
        self.assertIn("Body", sent_message.get_content())

    def test_email_provider_missing_recipient_is_non_retryable(self):
        provider = EmailProvider("smtp.example.com", 587, "", "", sender="no-reply@example.com")

        with self.assertRaises(ProviderError) as raised:
            provider.send("", "Subject", "Body")

        self.assert_provider_error(
            raised.exception,
            retryable=False,
            code="missing_email",
        )

    def test_email_provider_smtp_error_is_retryable(self):
        provider = EmailProvider("smtp.example.com", 587, "", "", sender="no-reply@example.com")

        with (
            patch(
                "notifications.services.providers.email.smtplib.SMTP",
                side_effect=OSError("network unreachable"),
            ),
            self.assertRaises(ProviderError) as raised,
        ):
            provider.send("user@example.com", "Subject", "Body")

        self.assert_provider_error(
            raised.exception,
            retryable=True,
            code="smtp_connection_error",
        )

    def test_sms_provider_success_returns_provider_message_id(self):
        provider = SmsProvider("AC123", "token", "+10000000000")
        response = self.twilio_response(payload={"sid": "SM123", "status": "queued"})

        with patch(
            "notifications.services.providers.sms_twilio.requests.post",
            return_value=response,
        ) as post:
            result = provider.send("+15551234567", "Hello")

        self.assertEqual(result.channel, "sms")
        self.assertEqual(result.provider_message_id, "SM123")
        self.assertEqual(result.raw_response, {"sid": "SM123", "status": "queued"})
        post.assert_called_once_with(
            "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json",
            data={"From": "+10000000000", "To": "+15551234567", "Body": "Hello"},
            auth=("AC123", "token"),
            timeout=15,
        )

    def test_sms_provider_missing_phone_is_non_retryable(self):
        provider = SmsProvider("AC123", "token", "+10000000000")

        with self.assertRaises(ProviderError) as raised:
            provider.send("", "Hello")

        self.assert_provider_error(
            raised.exception,
            retryable=False,
            code="missing_phone",
        )

    def test_sms_provider_400_is_non_retryable(self):
        provider = SmsProvider("AC123", "token", "+10000000000")
        response = self.twilio_response(
            ok=False,
            status_code=400,
            payload={"message": "Invalid To number"},
        )

        with (
            patch(
                "notifications.services.providers.sms_twilio.requests.post",
                return_value=response,
            ),
            self.assertRaises(ProviderError) as raised,
        ):
            provider.send("+15551234567", "Hello")

        self.assert_provider_error(
            raised.exception,
            retryable=False,
            code="twilio_http_400",
        )

    def test_sms_provider_429_and_500_are_retryable(self):
        provider = SmsProvider("AC123", "token", "+10000000000")

        for status_code in (429, 500):
            response = self.twilio_response(
                ok=False,
                status_code=status_code,
                payload={"message": "Temporary failure"},
            )
            with (
                patch(
                    "notifications.services.providers.sms_twilio.requests.post",
                    return_value=response,
                ),
                self.assertRaises(ProviderError) as raised,
            ):
                provider.send("+15551234567", "Hello")

            self.assert_provider_error(
                raised.exception,
                retryable=True,
                code=f"twilio_http_{status_code}",
            )

    def test_telegram_provider_success_returns_message_id(self):
        provider = TelegramProvider("bot-token")
        response = self.telegram_response(payload={"ok": True, "result": {"message_id": 123}})

        with patch(
            "notifications.services.providers.telegram.requests.post",
            return_value=response,
        ) as post:
            result = provider.send("12345", "Hello")

        self.assertEqual(result.channel, "telegram")
        self.assertEqual(result.provider_message_id, "123")
        self.assertEqual(result.raw_response, {"ok": True, "result": {"message_id": 123}})
        post.assert_called_once_with(
            "https://api.telegram.org/botbot-token/sendMessage",
            json={"chat_id": "12345", "text": "Hello"},
            timeout=10,
        )

    def test_telegram_provider_missing_chat_id_is_non_retryable(self):
        provider = TelegramProvider("bot-token")

        with self.assertRaises(ProviderError) as raised:
            provider.send("", "Hello")

        self.assert_provider_error(
            raised.exception,
            retryable=False,
            code="missing_chat_id",
        )

    def test_telegram_provider_400_is_non_retryable(self):
        provider = TelegramProvider("bot-token")
        response = self.telegram_response(
            ok=False,
            status_code=400,
            payload={"description": "Bad Request: chat not found"},
        )

        with (
            patch(
                "notifications.services.providers.telegram.requests.post",
                return_value=response,
            ),
            self.assertRaises(ProviderError) as raised,
        ):
            provider.send("12345", "Hello")

        self.assert_provider_error(
            raised.exception,
            retryable=False,
            code="telegram_http_400",
        )

    def test_telegram_provider_429_and_500_are_retryable(self):
        provider = TelegramProvider("bot-token")

        for status_code in (429, 500):
            response = self.telegram_response(
                ok=False,
                status_code=status_code,
                payload={"description": "Temporary failure"},
            )
            with (
                patch(
                    "notifications.services.providers.telegram.requests.post",
                    return_value=response,
                ),
                self.assertRaises(ProviderError) as raised,
            ):
                provider.send("12345", "Hello")

            self.assert_provider_error(
                raised.exception,
                retryable=True,
                code=f"telegram_http_{status_code}",
            )


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
            with self.assertRaises(RuntimeError):
                send_notification_task(notification.id)
            with self.assertRaises(RuntimeError):
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
            with self.assertRaises(RuntimeError):
                send_notification_task(notification.id)
            with self.assertRaises(RuntimeError):
                send_notification_task(notification.id)

            self.assertFalse(send_notification_task(notification.id))

        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationStatus.FAILED)
        self.assertEqual(
            DeliveryAttempt.objects.filter(notification=notification, success=False).count(),
            3,
        )

    def test_non_retryable_provider_error_falls_back_without_retrying_channel(self):
        user = User.objects.create(phone="+15551234567", channel_priority="email,sms")
        notification = Notification.objects.create(user=user, subject="Hello", message="Body")
        email_provider = Mock()
        email_provider.send.side_effect = ProviderError(
            "Recipient email is empty",
            retryable=False,
            code="missing_email",
        )
        sms_provider = Mock()

        with patch(
            "notifications.tasks.get_provider",
            side_effect=lambda channel: {"email": email_provider, "sms": sms_provider}[channel],
        ):
            self.assertTrue(send_notification_task(notification.id))

        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationStatus.SENT)
        email_provider.send.assert_called_once()
        sms_provider.send.assert_called_once()
        self.assertEqual(
            DeliveryAttempt.objects.filter(
                notification=notification,
                channel="email",
                success=False,
            ).count(),
            1,
        )
        self.assertEqual(
            DeliveryAttempt.objects.filter(
                notification=notification,
                channel="sms",
                success=True,
            ).count(),
            1,
        )


class EnqueueNotificationTests(TestCase):
    def test_idempotency_key_returns_existing_notification_without_requeueing(self):
        user = User.objects.create(email="user@example.com")

        with patch("notifications.services.producer.schedule_outbox_dispatch") as dispatch:
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
        outbox = NotificationOutbox.objects.get(notification=first)
        dispatch.assert_called_once_with(outbox.id)

    def test_outbox_dispatch_publishes_notification_task(self):
        user = User.objects.create(email="user@example.com")
        notification = Notification.objects.create(user=user, subject="Hello", message="Body")
        outbox = NotificationOutbox.objects.create(notification=notification)

        with patch("notifications.tasks.send_notification_task.delay") as delay:
            published = dispatch_notification_outbox_task(outbox_id=outbox.id)

        outbox.refresh_from_db()
        self.assertEqual(published, 1)
        self.assertEqual(outbox.status, NotificationOutboxStatus.PUBLISHED)
        self.assertEqual(outbox.attempts, 1)
        delay.assert_called_once_with(notification.id)

    def test_outbox_dispatch_keeps_failed_publish_for_recovery(self):
        user = User.objects.create(email="user@example.com")
        notification = Notification.objects.create(user=user, subject="Hello", message="Body")
        outbox = NotificationOutbox.objects.create(notification=notification)

        with patch(
            "notifications.tasks.send_notification_task.delay",
            side_effect=RuntimeError("broker down"),
        ):
            published = dispatch_notification_outbox_task(outbox_id=outbox.id)

        outbox.refresh_from_db()
        self.assertEqual(published, 0)
        self.assertEqual(outbox.status, NotificationOutboxStatus.FAILED)
        self.assertEqual(outbox.attempts, 1)
        self.assertIn("broker down", outbox.last_error)

    def test_periodic_outbox_recovery_publishes_failed_rows(self):
        user = User.objects.create(email="user@example.com")
        notification = Notification.objects.create(user=user, subject="Hello", message="Body")
        outbox = NotificationOutbox.objects.create(
            notification=notification,
            status=NotificationOutboxStatus.FAILED,
            attempts=2,
            last_error="broker down",
        )

        with patch("notifications.tasks.send_notification_task.delay") as delay:
            published = dispatch_notification_outbox_task(limit=100)

        outbox.refresh_from_db()
        self.assertEqual(published, 1)
        self.assertEqual(outbox.status, NotificationOutboxStatus.PUBLISHED)
        self.assertEqual(outbox.attempts, 3)
        self.assertEqual(outbox.last_error, "")
        delay.assert_called_once_with(notification.id)

    def test_periodic_outbox_recovery_respects_batch_limit(self):
        user = User.objects.create(email="user@example.com")
        first = Notification.objects.create(user=user, subject="First", message="Body")
        second = Notification.objects.create(user=user, subject="Second", message="Body")
        first_outbox = NotificationOutbox.objects.create(notification=first)
        second_outbox = NotificationOutbox.objects.create(notification=second)

        with patch("notifications.tasks.send_notification_task.delay") as delay:
            published = dispatch_notification_outbox_task(limit=1)

        first_outbox.refresh_from_db()
        second_outbox.refresh_from_db()
        self.assertEqual(published, 1)
        self.assertEqual(first_outbox.status, NotificationOutboxStatus.PUBLISHED)
        self.assertEqual(second_outbox.status, NotificationOutboxStatus.PENDING)
        delay.assert_called_once_with(first.id)

    def test_outbox_recovery_is_registered_in_celery_beat_schedule(self):
        schedule = settings.CELERY_BEAT_SCHEDULE["notification-outbox-recovery"]

        self.assertEqual(schedule["task"], "notifications.tasks.dispatch_notification_outbox_task")
        self.assertEqual(
            schedule["schedule"],
            settings.CELERY_OUTBOX_DISPATCH_INTERVAL_SECONDS,
        )
        self.assertEqual(
            schedule["kwargs"],
            {"limit": settings.CELERY_OUTBOX_DISPATCH_BATCH_SIZE},
        )


class SeedDemoCommandTests(TestCase):
    def test_seed_demo_creates_user_and_notification(self):
        out = StringIO()

        with (
            patch("notifications.services.producer.schedule_outbox_dispatch") as dispatch,
            self.captureOnCommitCallbacks(execute=True),
        ):
            call_command("seed_demo", stdout=out)

        self.assertIn("Demo notification enqueued.", out.getvalue())
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 1)
        outbox = NotificationOutbox.objects.get(notification=Notification.objects.get())
        dispatch.assert_called_once_with(outbox.id)

    def test_seed_demo_reuses_fixed_idempotency_key(self):
        out = StringIO()

        with patch("notifications.services.producer.schedule_outbox_dispatch") as dispatch:
            with self.captureOnCommitCallbacks(execute=True):
                call_command("seed_demo", "--idempotency-key=demo-fixed", stdout=out)
            with self.captureOnCommitCallbacks(execute=True):
                call_command("seed_demo", "--idempotency-key=demo-fixed", stdout=out)

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 1)
        outbox = NotificationOutbox.objects.get(notification=Notification.objects.get())
        dispatch.assert_called_once_with(outbox.id)


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
        with (
            patch("notifications.services.producer.schedule_outbox_dispatch") as dispatch,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                "/api/notifications/",
                {"user_id": self.user.id, "message": "Hello"},
                format="json",
                HTTP_X_API_KEY="test-notification-api-key",
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Notification.objects.count(), 1)
        outbox = NotificationOutbox.objects.get(notification=Notification.objects.get())
        dispatch.assert_called_once_with(outbox.id)

    def test_notification_endpoint_is_throttled(self):
        cache.clear()

        with (
            patch("notifications.services.producer.schedule_outbox_dispatch"),
            patch("rest_framework.throttling.ScopedRateThrottle.get_rate", return_value="1/min"),
        ):
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


class SystemEndpointTests(TestCase):
    def test_root_redirects_to_swagger_ui(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/api/docs/")

    def test_swagger_ui_alias_is_available(self):
        response = self.client.get("/api/schema/swagger-ui/")

        self.assertEqual(response.status_code, 200)

    @override_settings(ENABLE_GRAPHIQL=True)
    def test_graphql_playground_is_available_when_enabled(self):
        response = self.client.get("/graphql", HTTP_ACCEPT="text/html")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])

    def test_openapi_schema_documents_public_surface(self):
        response = self.client.get("/api/schema/", HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, 200)
        schema = json.loads(response.content)
        paths = schema["paths"]

        self.assertIn("/api/notifications/", paths)
        self.assertIn("/api/notifications/{id}/", paths)
        self.assertIn("/health/live", paths)
        self.assertIn("/health/ready", paths)
        self.assertNotIn("/metrics", paths)
        self.assertNotIn("/webhooks/telegram/", paths)
        self.assertNotIn("/graphql", paths)

        post_notification = paths["/api/notifications/"]["post"]
        self.assertEqual(post_notification["tags"], ["Notifications"])
        self.assertEqual(post_notification["security"], [{"ApiKeyAuth": []}])
        self.assertIn("400", post_notification["responses"])
        self.assertIn("401", post_notification["responses"])
        self.assertIn("429", post_notification["responses"])
        self.assertIn(
            "ValidationError",
            post_notification["responses"]["400"]["content"]["application/json"]["examples"],
        )

        live = paths["/health/live"]["get"]
        self.assertEqual(live["tags"], ["System"])
        self.assertEqual(live.get("security", []), [])

        components = schema["components"]
        self.assertIn("ApiKeyAuth", components["securitySchemes"])
        self.assertIn("HealthLive", components["schemas"])
        self.assertIn("HealthReady", components["schemas"])
        self.assertIn("user_id", components["schemas"]["ValidationError"]["properties"])

    def test_liveness_endpoint_returns_ok(self):
        response = self.client.get("/health/live")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness_endpoint_checks_dependencies(self):
        response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"]["database"], True)
        self.assertEqual(response.json()["checks"]["cache"], True)

    def test_metrics_requires_api_key(self):
        response = self.client.get("/metrics")

        self.assertEqual(response.status_code, 401)

    def test_metrics_accepts_api_key(self):
        response = self.client.get("/metrics", HTTP_X_API_KEY="test-notification-api-key")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response["Content-Type"])

    def test_metrics_include_outbox_rows_by_status(self):
        user = User.objects.create(email="metrics@example.com")
        notification = Notification.objects.create(user=user, subject="Hello", message="Body")
        NotificationOutbox.objects.create(notification=notification)

        response = self.client.get("/metrics", HTTP_X_API_KEY="test-notification-api-key")
        body = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('notification_outbox_rows_total{status="pending"} 1.0', body)
        self.assertIn("notification_outbox_oldest_pending_age_seconds", body)

    def test_metrics_include_failed_outbox_publish_attempts(self):
        user = User.objects.create(email="metrics@example.com")
        notification = Notification.objects.create(user=user, subject="Hello", message="Body")
        outbox = NotificationOutbox.objects.create(
            notification=notification,
            created_at=timezone.now() - timedelta(seconds=60),
        )

        with patch(
            "notifications.tasks.send_notification_task.delay",
            side_effect=RuntimeError("broker down"),
        ):
            dispatch_notification_outbox_task(outbox_id=outbox.id)

        response = self.client.get("/metrics", HTTP_X_API_KEY="test-notification-api-key")
        body = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('notification_outbox_rows_total{status="failed"} 1.0', body)
        self.assertIn(
            'notification_outbox_publish_attempts_total{status="failed"}',
            body,
        )


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
            "/webhooks/telegram/",
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
            "/webhooks/telegram/",
            json.dumps(self.telegram_update()),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    @override_settings(TELEGRAM_WEBHOOK_SECRET="")
    def test_start_command_parser_accepts_bot_username(self):
        response = self.client.post(
            "/webhooks/telegram/",
            json.dumps(self.telegram_update(text="/start@NotificationBot deep-link")),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 1)

    @override_settings(TELEGRAM_WEBHOOK_SECRET="expected-secret")
    def test_rejects_invalid_telegram_secret(self):
        response = self.client.post(
            "/webhooks/telegram/",
            json.dumps(self.telegram_update()),
            content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong-secret",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(User.objects.count(), 0)

    @override_settings(TELEGRAM_WEBHOOK_SECRET="", TELEGRAM_WEBHOOK_MAX_BODY_BYTES=10)
    def test_rejects_large_telegram_payload(self):
        response = self.client.post(
            "/webhooks/telegram/",
            json.dumps(self.telegram_update()),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(User.objects.count(), 0)

    @override_settings(TELEGRAM_WEBHOOK_SECRET="")
    def test_ignores_non_start_messages(self):
        response = self.client.post(
            "/webhooks/telegram/",
            json.dumps(self.telegram_update(text="hello")),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)
