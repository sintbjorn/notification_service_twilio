# Production Checklist

This checklist describes what should be verified before running Notification Service in a
production-like environment.

It is intentionally practical: each item maps to a real setting, endpoint, command, or
operational behavior in this repository.

## 1. Required Environment

Use production settings:

```text
DJANGO_SETTINGS_MODULE=notifier.settings.production
```

Required production variables:

```text
DJANGO_SECRET_KEY=<strong-random-secret>
DJANGO_ALLOWED_HOSTS=notifications.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://notifications.example.com
NOTIFICATION_API_KEY=<strong-service-api-key>
METRICS_API_KEY=<strong-metrics-api-key>
DATABASE_URL=postgres://user:password@postgres:5432/notif
REDIS_URL=redis://redis:6379/0
```

Recommended production variables:

```text
DJANGO_SECURE_SSL_REDIRECT=1
DJANGO_SECURE_HSTS_SECONDS=31536000
ENABLE_GRAPHIQL=0
LOG_LEVEL=INFO
NOTIFICATION_THROTTLE_RATE=60/min
CELERY_OUTBOX_DISPATCH_INTERVAL_SECONDS=60
CELERY_OUTBOX_DISPATCH_BATCH_SIZE=100
```

Provider variables:

```text
SMTP_HOST=<smtp-host>
SMTP_PORT=587
SMTP_USER=<smtp-user>
SMTP_PASSWORD=<smtp-password>
SMTP_SENDER=no-reply@example.com

TWILIO_SID=<twilio-account-sid>
TWILIO_TOKEN=<twilio-auth-token>
TWILIO_FROM=<verified-sender-number>

TELEGRAM_BOT_TOKEN=<telegram-bot-token>
TELEGRAM_WEBHOOK_SECRET=<strong-random-secret>
TELEGRAM_WEBHOOK_MAX_BODY_BYTES=65536
```

## 2. Security Checklist

- `DEBUG` must be disabled.
- `DJANGO_SECRET_KEY` must not use the development fallback.
- `DJANGO_ALLOWED_HOSTS` must be explicit.
- `NOTIFICATION_API_KEY` must be strong and rotated through a secret manager.
- `METRICS_API_KEY` should be separate from `NOTIFICATION_API_KEY`.
- `ENABLE_GRAPHIQL` must be disabled unless the environment is explicitly internal.
- Telegram webhook must use `X-Telegram-Bot-Api-Secret-Token`.
- Provider credentials must come only from environment variables or a secret manager.
- `/metrics` must not be publicly accessible without a key or allowlist.
- TLS should terminate at the edge proxy or load balancer.
- `SECURE_SSL_REDIRECT`, secure cookies, HSTS, and content type nosniff should be enabled.
- Docker application containers should run as a non-root user.

## 3. Database and Migrations

Before deploy:

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
```

Verify important tables exist:

- `notifications_user`
- `notifications_notification`
- `notifications_notificationoutbox`
- `notifications_deliveryattempt`

Operational rule:

- Never delete failed notifications to retry delivery.
- Use admin clone action or create a new notification so audit history stays intact.

## 4. Runtime Services

Required processes:

- Django/Gunicorn web process.
- Celery worker.
- Celery beat.
- PostgreSQL.
- Redis.
- Reverse proxy or load balancer.

Local equivalent:

```bash
make ps
```

Production expectation:

- Web process is healthy.
- Worker process is consuming tasks.
- Beat process is publishing scheduled outbox recovery tasks.
- PostgreSQL has backups enabled.
- Redis persistence or managed Redis durability policy is understood.

## 5. Health Checks

Liveness:

```bash
curl -fsS https://notifications.example.com/health/live
```

Expected:

```json
{"status":"ok"}
```

Readiness:

```bash
curl -fsS https://notifications.example.com/health/ready
```

Expected:

```json
{"status":"ok","checks":{"database":true,"cache":true}}
```

Use `/health/live` for process restarts and `/health/ready` for traffic routing.

## 6. Metrics

Prometheus scrape:

```bash
curl -fsS https://notifications.example.com/metrics \
  -H "X-API-Key: $METRICS_API_KEY"
```

Core metrics:

```text
notifications_sent_total
notifications_failed_total
delivery_attempts_total{channel,status}
notification_outbox_rows_total{status}
notification_outbox_publish_attempts_total{status}
notification_outbox_oldest_pending_age_seconds
```

Suggested alerts:

- `notification_outbox_rows_total{status="failed"} > 0` for more than 5 minutes.
- `notification_outbox_oldest_pending_age_seconds > 300`.
- `increase(notifications_failed_total[10m]) > 0`.
- High rate of `delivery_attempts_total{status="failed"}`.
- Readiness endpoint returns non-200.
- Celery worker process is down.
- Celery beat process is down.

## 7. Outbox Recovery

Automatic recovery is enabled through Celery beat:

```text
notification-outbox-recovery
```

Default behavior:

```text
Every 60 seconds, dispatch up to 100 pending or failed outbox rows.
```

Manual recovery:

```bash
python manage.py dispatch_outbox
```

Production expectation:

- Pending outbox rows should normally be short-lived.
- Failed outbox rows should recover when broker connectivity is restored.
- The dispatcher uses row locking to avoid duplicate publish when immediate and periodic
  dispatch overlap.

## 8. API Verification

Create notification:

```bash
curl -X POST https://notifications.example.com/api/notifications/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $NOTIFICATION_API_KEY" \
  -H "X-Request-ID: prod-smoke-001" \
  -d '{
    "user_id": 1,
    "subject": "Production smoke test",
    "message": "Notification pipeline is reachable.",
    "idempotency_key": "prod-smoke-001"
  }'
```

Retrieve status:

```bash
curl -fsS https://notifications.example.com/api/notifications/1/ \
  -H "X-API-Key: $NOTIFICATION_API_KEY"
```

Expected statuses:

```text
queued -> processing -> sent
queued -> processing -> failed
```

## 9. Webhook Verification

Telegram webhook endpoint:

```text
POST /webhooks/telegram/
```

Production checks:

- Endpoint is not exposed in public OpenAPI docs.
- `TELEGRAM_WEBHOOK_SECRET` is configured.
- Telegram webhook uses `secret_token`.
- Invalid secret returns `403`.
- Large payloads return `413`.
- Non-JSON payloads return `415`.

## 10. Logging

Logs should be structured JSON on stdout.

Important events:

```text
notification.created
notification.outbox_published
notification.outbox_publish_failed
notification.processing
notification.channel_attempt
notification.retry_scheduled
notification.sent
notification.failed
telegram.update_received
telegram.user_onboarded
```

Operational fields to index:

- `request_id`
- `notification_id`
- `outbox_id`
- `user_id`
- `channel`
- `attempt`
- `status`
- `error`
- `retryable`

## 11. Backup and Restore

PostgreSQL is the source of truth.

Back up:

- users,
- notifications,
- outbox rows,
- delivery attempts,
- Django auth/admin tables if admin access matters.

Restore expectations:

- Published outbox rows should not be republished.
- Pending or failed outbox rows can be recovered by Celery beat or `dispatch_outbox`.
- Delivery attempts remain available for audit history.

## 12. Deployment Smoke Test

After deploy:

```bash
curl -fsS https://notifications.example.com/health/live
curl -fsS https://notifications.example.com/health/ready
curl -fsS https://notifications.example.com/metrics -H "X-API-Key: $METRICS_API_KEY" | head
```

Then:

1. Create a notification with a unique idempotency key.
2. Confirm a `NotificationOutbox` row is published.
3. Confirm worker logs show `notification.sent` or a clear provider failure.
4. Confirm `DeliveryAttempt` exists.
5. Confirm metrics changed.

## 13. Rollback Notes

If a deployment is rolled back:

- Do not delete new outbox rows.
- Keep Celery beat and worker compatible with the deployed database schema.
- If migrations introduced new required fields, roll back application and schema together.
- Run `dispatch_outbox` after recovery if broker publish was interrupted.

## 14. Portfolio Review Notes

For a reviewer, the production signals are:

- Separate `local`, `test`, and `production` settings.
- Strict production startup checks.
- Non-root Docker runtime.
- Health checks with dependency readiness.
- Protected metrics.
- Durable outbox with periodic recovery.
- Idempotency.
- Structured logs.
- Admin operational views.
- CI with linting, audit, migrations, coverage, and Docker build.
