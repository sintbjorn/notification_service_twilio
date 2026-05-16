import json
import logging
from datetime import datetime, timezone

from .request_context import get_request_id

RESERVED_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class RequestIDFilter(logging.Filter):
    def filter(self, record):
        record.request_id = getattr(record, "request_id", "") or get_request_id()
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", "")
        if request_id:
            payload["request_id"] = request_id

        for key, value in record.__dict__.items():
            if key not in RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)
