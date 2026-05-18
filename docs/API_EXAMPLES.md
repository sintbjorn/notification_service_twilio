# API Examples

This document contains copy-paste examples for manually exercising the Notification
Service API during development, QA, or portfolio review.

Local base URL:

```text
http://localhost:8000
```

Local API key:

```text
dev-notification-api-key
```

## 1. Create Demo Data

The easiest way to create a user and enqueue a notification through the real pipeline:

```bash
make demo
```

Fixed idempotency demo:

```bash
make demo-idempotent
make demo-idempotent
```

Both fixed-key runs should return the same notification instead of creating duplicates.

## 2. REST: Create Notification

```bash
curl -X POST http://localhost:8000/api/notifications/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-notification-api-key" \
  -H "X-Request-ID: api-example-create-001" \
  -d '{
    "user_id": 1,
    "subject": "Inspection report ready",
    "message": "Your inspection report is ready to review.",
    "idempotency_key": "api-example-create-001"
  }'
```

Example response:

```json
{
  "id": 1,
  "user": 1,
  "subject": "Inspection report ready",
  "message": "Your inspection report is ready to review.",
  "status": "queued",
  "created_at": "2026-05-18T13:00:00Z"
}
```

## 3. REST: Retrieve Notification

```bash
curl -fsS http://localhost:8000/api/notifications/1/ \
  -H "X-API-Key: dev-notification-api-key" \
  -H "X-Request-ID: api-example-get-001"
```

Example response:

```json
{
  "id": 1,
  "user": 1,
  "subject": "Inspection report ready",
  "message": "Your inspection report is ready to review.",
  "status": "sent",
  "created_at": "2026-05-18T13:00:00Z"
}
```

## 4. REST: Idempotency

Send the same `idempotency_key` twice:

```bash
curl -X POST http://localhost:8000/api/notifications/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-notification-api-key" \
  -d '{
    "user_id": 1,
    "subject": "Idempotency demo",
    "message": "First request.",
    "idempotency_key": "idempotency-example-001"
  }'

curl -X POST http://localhost:8000/api/notifications/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-notification-api-key" \
  -d '{
    "user_id": 1,
    "subject": "Idempotency demo changed",
    "message": "Second request should reuse the first notification.",
    "idempotency_key": "idempotency-example-001"
  }'
```

Expected behavior:

- the same notification is returned,
- no duplicate outbox row is created,
- no duplicate delivery task is queued.

## 5. REST: Validation Error

```bash
curl -i -X POST http://localhost:8000/api/notifications/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-notification-api-key" \
  -d '{
    "user_id": 999999,
    "message": "Unknown user"
  }'
```

Example response:

```json
{
  "user_id": ["User does not exist."]
}
```

## 6. REST: Unauthorized

Missing API key:

```bash
curl -i -X POST http://localhost:8000/api/notifications/ \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "message": "Missing API key"
  }'
```

Expected:

```text
401 Unauthorized
```

Invalid API key:

```bash
curl -i -X POST http://localhost:8000/api/notifications/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: wrong-key" \
  -d '{
    "user_id": 1,
    "message": "Invalid API key"
  }'
```

Expected:

```json
{
  "detail": "Invalid API key."
}
```

## 7. GraphQL: Create Notification

Open GraphiQL:

```text
http://localhost:8000/graphql
```

Mutation:

```graphql
mutation {
  createNotification(
    userId: 1
    subject: "GraphQL demo"
    message: "Created through GraphQL."
    idempotencyKey: "graphql-example-001"
  ) {
    id
    status
    subject
    message
  }
}
```

Example response:

```json
{
  "data": {
    "createNotification": {
      "id": "1",
      "status": "queued",
      "subject": "GraphQL demo",
      "message": "Created through GraphQL."
    }
  }
}
```

## 8. GraphQL: Retrieve Notification

```graphql
query {
  notification(id: 1) {
    id
    status
    subject
    message
  }
}
```

## 9. Telegram Webhook: Start Command

The Telegram webhook is intentionally hidden from public REST docs.

Local example with configured secret:

```bash
curl -i -X POST http://localhost:8000/webhooks/telegram/ \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: dev-telegram-webhook-secret" \
  -d '{
    "update_id": 1001,
    "message": {
      "message_id": 10,
      "chat": {
        "id": 12345,
        "type": "private"
      },
      "text": "/start"
    }
  }'
```

Example response:

```json
{
  "ok": true,
  "user_id": 1,
  "telegram_chat_id": "12345"
}
```

Invalid secret:

```bash
curl -i -X POST http://localhost:8000/webhooks/telegram/ \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: wrong-secret" \
  -d '{"update_id":1001}'
```

Expected:

```text
403 Forbidden
```

## 10. Health Checks

Liveness:

```bash
curl -fsS http://localhost:8000/health/live
```

Expected:

```json
{"status":"ok"}
```

Readiness:

```bash
curl -fsS http://localhost:8000/health/ready
```

Expected:

```json
{"status":"ok","checks":{"database":true,"cache":true}}
```

## 11. Metrics

Unauthorized:

```bash
curl -i http://localhost:8000/metrics
```

Expected:

```text
401 Unauthorized
```

Authorized:

```bash
curl -fsS http://localhost:8000/metrics \
  -H "X-API-Key: dev-notification-api-key"
```

Useful metrics:

```text
notifications_sent_total
notifications_failed_total
delivery_attempts_total{channel,status}
notification_outbox_rows_total{status}
notification_outbox_publish_attempts_total{status}
notification_outbox_oldest_pending_age_seconds
```

## 12. Outbox Recovery

Manual recovery:

```bash
make dispatch-outbox
```

Equivalent command:

```bash
docker compose exec web python manage.py dispatch_outbox
```

Recover a single outbox row:

```bash
docker compose exec web python manage.py dispatch_outbox --outbox-id=1
```

Automatic recovery runs through Celery beat every
`CELERY_OUTBOX_DISPATCH_INTERVAL_SECONDS`.

## 13. OpenAPI Schema

Swagger UI:

```text
http://localhost:8000/api/docs/
```

Schema JSON:

```bash
curl -fsS http://localhost:8000/api/schema/
```

Generate schema inside the container:

```bash
make openapi
```

The generated schema is written to:

```text
/tmp/openapi.json
```

inside the web container.

## 14. Admin Review

Open:

```text
http://localhost:8000/admin/
```

Create a superuser if needed:

```bash
make superuser
```

Recommended admin pages:

- Users.
- Notifications.
- Notification outbox rows.
- Delivery attempts.

## 15. Worker Logs

```bash
make logs-worker
```

Look for:

```text
notification.created
notification.outbox_published
notification.processing
notification.channel_attempt
notification.sent
notification.failed
```
