# Notification Service (Django + DRF + Celery + Redis + Postgres + GraphQL + Nginx)

Простой, **рабочий** сервис отправки уведомлений с fallback по каналам: **Email → SMS → Telegram**.
Собрано с комментариями и удобными инструкциями для запуска в **Docker**, тестировалось в Windows + VS Code (Docker Desktop).

## Что внутри
- **Django 4.2 + DRF** — REST API
- **Strawberry GraphQL** — точка входа GraphQL
- **Celery + Redis** — фоновая отправка, ретраи, backoff
- **PostgreSQL** — хранение пользователей и уведомлений
- **cacheops + django-redis** — кэш настроек
- **Nginx** — прокси к приложению
- **Mailhog** — тестовый SMTP (ловит письма локально на http://localhost:8025)

## Быстрый старт

1) Скопируй `.env.example` → `.env` (если хочешь, поправь значения):
```bash
cp .env.example .env
```

2) Подними окружение:
```bash
docker compose up --build
```

3) Применяй миграции:
```bash
docker compose exec web python manage.py migrate
```

4) Создай тестового пользователя (email/phone/telegram):
```bash
docker compose exec web python manage.py shell -c "from notifications.models import User; User.objects.create(email='me@example.com', phone='+420123456789', telegram_chat_id='12345')"
```

> Письма смотри в **Mailhog**: http://localhost:8025

5) Отправь уведомление (REST, DRF):
```bash
curl -X POST http://localhost:8000/api/notifications/ -H "Content-Type: application/json"   -d '{"user_id":1, "subject":"Hello", "message":"Test from DRF"}'
```

6) Или через GraphQL:
- Открой http://localhost:8000/graphql (GraphiQL)
- Запусти мутацию:
```graphql
mutation {
  createNotification(userId: 1, subject: "Hi", message: "From GraphQL") {
    id
    status
  }
}
```

7) Посмотреть статус уведомления (REST):
```bash
curl http://localhost:8000/api/notifications/1/
```

## Как это работает (коротко)

- Запрос на создание уведомления кладёт задачу в Celery (`send_notification_task`).
- Задача перебирает каналы пользователя по приоритету (`User.channel_priority`).
- На каждом канале до 3 попыток + backoff от Celery. Если канал не взлетел — переходим к следующему.
- При успехе статус `sent`, при полном провале по всем каналам — `failed`.
- Все попытки пишутся в `DeliveryAttempt` (для аудита и отладки).

## Где смотреть код

- Модели: `notifications/models.py`
- DRF сериалайзеры/вьюхи: `notifications/serializers.py`, `notifications/views.py`
- Celery задача: `notifications/tasks.py`
- Провайдеры каналов: `notifications/services/providers.py`
- Фабрика провайдеров: `notifications/services/factory.py`
- Публикация задач (outbox-подход): `notifications/services/producer.py`
- GraphQL схема: `notifications/schema.py`
- Настройки Django/Celery/Redis: `notifier/settings.py`
- Docker/Compose/Nginx: `Dockerfile`, `docker-compose.yml`, `deploy/nginx.conf`

## Пояснения по провайдерам

- **Email** — отправка через SMTP. В докере используется Mailhog, потому письма «ловятся» локально.
- **SMS** — заглушка (эмулирует ошибку для номеров, начинающихся на `+000`). Для боевого режима можно вставить вызов Twilio / другого провайдера.
- **Telegram** — реальный запрос к Bot API. Для полного теста нужен **настоящий** `TELEGRAM_BOT_TOKEN` и `telegram_chat_id` пользователя (чат с ботом должен быть начат).

## Типичные команды для разработки

- Миграции:
```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
```

- Создать суперпользователя (для /admin):
```bash
docker compose exec web python manage.py createsuperuser
```

- Логи Celery:
```bash
docker compose logs -f worker
```

- Проверка health:
```bash
curl http://localhost:8000/healthz
```

## Что ещё можно добавить (если будет время)

- Идемпотентность на уровне HTTP (заголовок `Idempotency-Key` → поле `idempotency_key`).
- Ограничение частоты (throttling) на API.
- Пагинация/фильтры списка уведомлений.
- События/вебхуки о статусах.
- Поддержка S3/SES (AWS) через переменные окружения.
- Полноценные интеграционные тесты с моками провайдеров.



## Настройка Twilio (реальная отправка SMS)
1) Зарегистрируйся в Twilio и получи **Account SID** и **Auth Token**.
2) Верифицируй отправителя (**TWILIO_FROM**) и получателя (в trial-аккаунте).
3) Заполни в `.env`:
```
TWILIO_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_TOKEN=your_auth_token
TWILIO_FROM=+1XXXXXXXXXX
```
4) Перезапусти сервисы (или `docker compose up --build -d`).
5) Укажи валидный номер телефона у пользователя и отправь уведомление.
