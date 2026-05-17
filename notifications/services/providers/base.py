from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderResult:
    channel: str
    provider_message_id: str = ""
    raw_response: dict[str, Any] | None = None


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = True, code: str = ""):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


class NotificationProvider(Protocol):
    channel: str

