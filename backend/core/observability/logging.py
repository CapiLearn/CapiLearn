import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from backend.core.config import Settings, settings
from backend.core.observability.context import get_request_id

_RESERVED_ATTRS = set(logging.makeLogRecord({}).__dict__)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or get_request_id()
        if request_id is not None:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and key not in payload:
                payload[key] = _json_safe(value)

        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return True


def configure_logging(config: Settings = settings) -> None:
    level = getattr(logging, config.log_level)
    formatter: logging.Formatter
    if config.log_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] [request_id=%(request_id)s] %(message)s"
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    exc_info: bool | BaseException | tuple | None = None,
    **fields: Any,
) -> None:
    if not settings.observability_enabled:
        return
    payload = {"event": event, **fields}
    if "request_id" not in payload:
        payload["request_id"] = get_request_id()
    logger.log(level, event, extra=payload, exc_info=exc_info)


def _json_safe(value: Any) -> Any:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return str(value)
