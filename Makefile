COMPOSE ?= docker compose
TEST_PROJECT ?= notification_service_twilio_test
API_KEY ?= dev-notification-api-key
DEMO_IDEMPOTENCY_KEY ?= portfolio-demo-001

.PHONY: help up rebuild down restart ps logs logs-web logs-worker logs-beat migrate makemigrations superuser shell demo demo-idempotent dispatch-outbox health metrics test test-compose lint format-check openapi

help:
	@printf "Notification Service commands:\n\n"
	@printf "  make up                 Start the Docker Compose stack in the background\n"
	@printf "  make rebuild            Rebuild images and start the stack\n"
	@printf "  make down               Stop containers\n"
	@printf "  make restart            Restart the stack\n"
	@printf "  make ps                 Show container status\n"
	@printf "  make migrate            Apply Django migrations\n"
	@printf "  make makemigrations     Create Django migrations\n"
	@printf "  make superuser          Create a Django admin user\n"
	@printf "  make shell              Open Django shell inside the web container\n"
	@printf "  make demo               Seed demo user and notification\n"
	@printf "  make demo-idempotent    Seed demo using a fixed idempotency key\n"
	@printf "  make dispatch-outbox    Force outbox recovery now\n"
	@printf "  make health             Check live and ready endpoints\n"
	@printf "  make metrics            Fetch Prometheus metrics with API key\n"
	@printf "  make logs-worker        Follow Celery worker logs\n"
	@printf "  make test               Run Django tests in the running web container\n"
	@printf "  make test-compose       Run tests in an isolated Compose project\n"
	@printf "  make lint               Run Ruff linting locally\n"
	@printf "  make format-check       Run Ruff format check locally\n"
	@printf "  make openapi            Generate OpenAPI schema inside the web container\n"

up:
	$(COMPOSE) up -d

rebuild:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart: down up

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f

logs-web:
	$(COMPOSE) logs -f web

logs-worker:
	$(COMPOSE) logs -f worker

logs-beat:
	$(COMPOSE) logs -f beat

migrate:
	$(COMPOSE) exec web python manage.py migrate

makemigrations:
	$(COMPOSE) exec web python manage.py makemigrations

superuser:
	$(COMPOSE) exec web python manage.py createsuperuser

shell:
	$(COMPOSE) exec web python manage.py shell

demo:
	$(COMPOSE) exec web python manage.py seed_demo

demo-idempotent:
	$(COMPOSE) exec web python manage.py seed_demo --idempotency-key=$(DEMO_IDEMPOTENCY_KEY)

dispatch-outbox:
	$(COMPOSE) exec web python manage.py dispatch_outbox

health:
	@curl -fsS http://localhost:8000/health/live
	@printf "\n"
	@curl -fsS http://localhost:8000/health/ready
	@printf "\n"

metrics:
	@curl -fsS http://localhost:8000/metrics -H "X-API-Key: $(API_KEY)"

test:
	$(COMPOSE) exec web env DJANGO_SETTINGS_MODULE=notifier.settings.test python manage.py test notifications

test-compose:
	docker compose -p $(TEST_PROJECT) -f docker-compose.yml -f docker-compose.test.yml run --rm web python manage.py test notifications

lint:
	ruff check .

format-check:
	ruff format --check .

openapi:
	$(COMPOSE) exec web python manage.py spectacular --format openapi-json --file /tmp/openapi.json
