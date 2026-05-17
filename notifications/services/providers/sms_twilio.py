import requests

from .base import ProviderError, ProviderResult


class SmsProvider:
    channel = "sms"

    def __init__(self, account_sid, auth_token, from_number):
        self.sid = account_sid
        self.token = auth_token
        self.from_number = from_number

    def send(self, to_phone: str, body: str) -> ProviderResult:
        if not to_phone:
            raise ProviderError("Recipient phone is empty", retryable=False, code="missing_phone")

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json"
        data = {
            "From": self.from_number,
            "To": to_phone,
            "Body": body,
        }

        try:
            response = requests.post(url, data=data, auth=(self.sid, self.token), timeout=15)
        except requests.RequestException as exc:
            raise ProviderError(
                f"Twilio request failed: {exc}",
                retryable=True,
                code="twilio_request_failed",
            ) from exc

        if not response.ok:
            message = _twilio_error_message(response)
            retryable = response.status_code == 429 or 500 <= response.status_code < 600
            raise ProviderError(
                f"Twilio error: HTTP {response.status_code} - {message}",
                retryable=retryable,
                code=f"twilio_http_{response.status_code}",
            )

        payload = _safe_json(response)
        return ProviderResult(
            channel=self.channel,
            provider_message_id=str(payload.get("sid", "")),
            raw_response=payload or None,
        )


def _twilio_error_message(response) -> str:
    payload = _safe_json(response)
    return str(payload.get("message") or response.text)


def _safe_json(response) -> dict:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}
