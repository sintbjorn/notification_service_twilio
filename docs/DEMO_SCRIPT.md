# Demo Script

This script is a guided portfolio walkthrough for the Notification Service. It is written
for reviewers, interviewers, or maintainers who want to verify the backend behavior in a
short, repeatable session.

Estimated time: 5-10 minutes.

## What This Demo Proves

The demo shows that the project is more than a CRUD API:

- REST API is documented through Swagger/OpenAPI.
- Notifications are persisted before delivery.
- Delivery runs asynchronously through Celery.
- Email delivery can be inspected locally through Mailpit.
- Idempotency prevents duplicate notification creation.
- Outbox recovery is available automatically through Celery beat and manually through a
  management command.
- Health checks distinguish liveness from readiness.
- Prometheus metrics are protected with an API key.
- Django admin exposes an operational view of users, notifications, outbox rows, and
  delivery attempts.

## Prerequisites

Required tools:

- Docker
- Docker Compose
- Make

Create the local environment file if it does not exist:

```bash
cp .env.example .env
```

The local development API key is:

```text
dev-notification-api-key
```

## 1. Start the Stack

```bash
make rebuild
```

Check containers:

```bash
make ps
```

Expected services:

```text
web
worker
beat
db
redis
nginx
mailpit
```

The `web`, `db`, and `redis` services should become healthy.

## 2. Apply Migrations

```bash
make migrate
```

This creates the notification tables, including:

- users,
- notifications,
- delivery attempts,
- durable outbox rows.

## 3. Open Swagger

Open:

```text
http://localhost:8000/api/docs/
```

Show:

- `POST /api/notifications/`
- `GET /api/notifications/{id}/`
- `System` health endpoints
- `ApiKeyAuth`
- examples for success and common errors
- schemas for validation and health responses

Important note: `/webhooks/telegram/`, `/metrics`, and `/graphql` are intentionally not
part of the public REST docs.

## 4. Create a Demo Notification

```bash
make demo
```

Expected output includes:

```text
Demo notification enqueued.
User: <id>
Notification: <id> [queued]
Idempotency key: <key>
```

Behind the scenes:

1. `seed_demo` creates or updates a demo user.
2. `enqueue_notification()` persists the notification.
3. A `NotificationOutbox` row is created in the same DB transaction.
4. The outbox dispatcher publishes the delivery task to Celery.
5. The worker sends the message through the first available channel.

## 5. Verify Email Delivery in Mailpit

Open:

```text
http://localhost:8025/
```

Expected result:

- A message from `no-reply@example.com`.
- Subject similar to `Portfolio demo notification`.
- Body mentioning the asynchronous notification pipeline.

This proves the local SMTP delivery path works without sending real email.

## 6. Verify Idempotency

Run the fixed-key demo twice:

```bash
make demo-idempotent
make demo-idempotent
```

Expected result:

- Both runs reuse the same `DEMO_IDEMPOTENCY_KEY`.
- The same notification is returned instead of creating duplicate delivery work.

Default fixed key:

```text
portfolio-demo-001
```

Override it if needed:

```bash
make demo-idempotent DEMO_IDEMPOTENCY_KEY=my-review-demo-001
```

## 7. Inspect Django Admin

Open:

```text
http://localhost:8000/admin/
```

If needed, create an admin user:

```bash
make superuser
```

Show these admin surfaces:

- Users: contact fields, channel priority, notification count.
- Notifications: status badge, idempotency key, attempt counters.
- Notification detail: inline delivery attempts.
- Outbox rows: pending/published/failed state, attempts, last error.
- Delivery attempts: channel, success badge, error preview.

This gives a reviewer an operational view of the system.

## 8. Check Health Endpoints

```bash
make health
```

Expected response:

```json
{"status":"ok"}
{"status":"ok","checks":{"database":true,"cache":true}}
```

Use:

- `/health/live` for process liveness.
- `/health/ready` for dependency readiness.

## 9. Check Secured Metrics

Unauthorized request should fail:

```bash
curl -i http://localhost:8000/metrics
```

Expected:

```text
401 Unauthorized
```

Authorized request:

```bash
make metrics
```

Look for:

```text
notifications_sent_total
notifications_failed_total
delivery_attempts_total
notification_outbox_rows_total
notification_outbox_publish_attempts_total
notification_outbox_oldest_pending_age_seconds
```

## 10. Show Outbox Recovery

Automatic recovery runs through Celery beat. The schedule is configured by:

```text
CELERY_OUTBOX_DISPATCH_INTERVAL_SECONDS=60
CELERY_OUTBOX_DISPATCH_BATCH_SIZE=100
```

Manual recovery is available for an immediate operator action:

```bash
make dispatch-outbox
```

This republishes pending or failed outbox rows without recreating notifications.

## 11. Watch Worker Logs

```bash
make logs-worker
```

Useful log events:

```text
notification.created
notification.outbox_published
notification.processing
notification.channel_attempt
notification.sent
notification.failed
notification.retry_scheduled
```

The logs are structured JSON and include operational fields such as `notification_id`,
`outbox_id`, `channel`, `attempt`, `status`, and `request_id`.

## 12. Run Tests

```bash
make test
```

Expected result:

```text
OK
```

For isolated Compose test runs:

```bash
make test-compose
```

## Review Checklist

Use this as a screenshot checklist for the portfolio:

- Swagger UI with `Notifications` and `System` tags.
- `POST /api/notifications/` expanded with examples and error responses.
- Mailpit inbox with delivered demo email.
- Django admin notification list with status and attempt counters.
- Django admin outbox list with `published` rows.
- `docker compose ps` or `make ps` showing all services.
- `/health/ready` response.
- `/metrics` authorized response.
- Worker logs showing outbox publish and delivery.

## Cleanup

Stop containers:

```bash
make down
```

Remove persistent data only when you intentionally want a clean local database and Redis:

```bash
docker compose down --volumes
```
