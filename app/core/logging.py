"""Structured logging and request-ID context.

* Production (``APP_ENV=production``) logs one JSON object per line to stdout.
* Other environments log a readable single-line format.
* The current request ID (set by the request-context middleware) is attached to every record
  through a ``ContextVar``, so it follows the request across ``await`` points without being
  passed around.

Modules obtain loggers with ``logging.getLogger(__name__)``. Pass structured context with
``extra={...}``; never log secrets, API keys or raw document content.
"""

import json
import logging
import sys
import uuid
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_SERVER_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

_CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"

# Attributes present on every LogRecord; anything else came from ``extra=``.
_RESERVED_RECORD_ATTRIBUTES = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "request_id",
    "taskName",
}


def generate_request_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str | None:
    return _request_id_var.get()


def set_request_id(request_id: str) -> Token[str | None]:
    return _request_id_var.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id_var.reset(token)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        context = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_RECORD_ATTRIBUTES and not key.startswith("_")
        }
        if context:
            payload["context"] = context
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(_CONSOLE_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = get_request_id() or "-"
        return super().format(record)


def configure_logging(settings: Settings) -> None:
    """Configure the root logger. Safe to call more than once (it replaces its handlers)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.is_production else ConsoleFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
        existing.close()
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    # Route the ASGI server's own logs through the same handler and format.
    for name in _SERVER_LOGGERS:
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.propagate = True
