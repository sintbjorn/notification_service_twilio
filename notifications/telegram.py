import json
import logging

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import User
from .services.providers import TelegramProvider

logger = logging.getLogger(__name__)


def _extract_message(update: dict) -> dict:
    return update.get("message") or update.get("edited_message") or {}


def _parse_command(text: str) -> tuple[str, str]:
    if not text.startswith("/"):
        return "", ""

    command_token, _, command_args = text.partition(" ")
    command = command_token.removeprefix("/").split("@", 1)[0].lower()
    return command, command_args.strip()


def _reply(chat_id: str, text: str) -> None:
    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    if not bot_token or bot_token.startswith("fake"):
        logger.info("telegram.reply_skipped", extra={"telegram_chat_id": chat_id})
        return
    TelegramProvider(bot_token).send(chat_id, text)


def _handle_start(chat_id: str, update_id: int | None = None) -> User:
    user, created = User.objects.get_or_create(
        telegram_chat_id=chat_id,
        defaults={"channel_priority": "telegram,email,sms"},
    )
    logger.info(
        "telegram.user_onboarded",
        extra={
            "telegram_chat_id": chat_id,
            "telegram_update_id": update_id,
            "user_id": user.id,
            "user_created": created,
        },
    )
    _reply(
        chat_id,
        "Telegram notifications are enabled. You can now receive fallback alerts here.",
    )
    return user


@csrf_exempt
@require_POST
def telegram_webhook(request: HttpRequest):
    expected_secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")
    provided_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")

    if expected_secret and provided_secret != expected_secret:
        logger.warning("telegram.webhook_forbidden")
        return JsonResponse({"detail": "Forbidden"}, status=403)

    if request.content_type != "application/json":
        return JsonResponse({"detail": "Unsupported content type"}, status=415)

    max_body_bytes = getattr(settings, "TELEGRAM_WEBHOOK_MAX_BODY_BYTES", 65536)
    if len(request.body) > max_body_bytes:
        return JsonResponse({"detail": "Payload too large"}, status=413)

    try:
        update = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    update_id = update.get("update_id")
    message = _extract_message(update)
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    text = (message.get("text") or "").strip()
    command, command_args = _parse_command(text)

    logger.info(
        "telegram.update_received",
        extra={
            "telegram_update_id": update_id,
            "telegram_chat_id": chat_id,
            "telegram_command": command,
        },
    )

    if not chat_id:
        return JsonResponse({"detail": "No chat id"}, status=200)

    if command == "start":
        user = _handle_start(chat_id, update_id=update_id)
        return JsonResponse({"ok": True, "user_id": user.id, "telegram_chat_id": chat_id})

    logger.info(
        "telegram.message_ignored",
        extra={
            "telegram_chat_id": chat_id,
            "telegram_command": command,
            "telegram_command_args": command_args[:80],
        },
    )
    return JsonResponse({"ok": True, "ignored": True})
