import requests

from .base import ProviderError, ProviderResult


class TelegramProvider:
    channel = "telegram"

    def __init__(self, bot_token):
        self.bot_token = bot_token

    def send(self, chat_id: str, body: str) -> ProviderResult:
        if not chat_id:
            raise ProviderError("Recipient chat_id is empty", retryable=False, code="missing_chat_id")

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            response = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": body,
                },
                timeout=10,
            )
        except requests.RequestException as exc:
            raise ProviderError(
                f"Telegram request failed: {exc}",
                retryable=True,
                code="telegram_request_failed",
            ) from exc

        if not response.ok:
            message = _telegram_error_message(response)
            retryable = response.status_code == 429 or 500 <= response.status_code < 600
            raise ProviderError(
                f"Telegram error: {message}",
                retryable=retryable,
                code=f"telegram_http_{response.status_code}",
            )

        payload = _safe_json(response)
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        return ProviderResult(
            channel=self.channel,
            provider_message_id=str(result.get("message_id", "")),
            raw_response=payload or None,
        )


def _telegram_error_message(response) -> str:
    payload = _safe_json(response)
    return str(payload.get("description") or response.text)


def _safe_json(response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}
