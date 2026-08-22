"""Structured JSON logging with context propagation and sanitization."""

from __future__ import annotations

import contextvars
import json
import logging
import logging.handlers
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("job_id", default=None)
_plugin_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("plugin_id", default=None)


@dataclass(frozen=True, slots=True)
class LogContext:
    correlation_id: str | None = None
    job_id: str | None = None
    plugin_id: str | None = None

    def install(self) -> tuple[contextvars.Token[str | None], ...]:
        return (
            _correlation_id.set(self.correlation_id),
            _job_id.set(self.job_id),
            _plugin_id.set(self.plugin_id),
        )

    @staticmethod
    def reset(tokens: tuple[contextvars.Token[str | None], ...]) -> None:
        _correlation_id.reset(tokens[0])
        _job_id.reset(tokens[1])
        _plugin_id.reset(tokens[2])


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": record.levelname,
            "subsystem": record.name,
            "message": record.getMessage(),
        }
        optional = {
            "correlation_id": _correlation_id.get(),
            "job_id": _job_id.get(),
            "plugin_id": _plugin_id.get(),
            "error_code": getattr(record, "error_code", None),
        }
        payload.update({key: value for key, value in optional.items() if value is not None})
        context = getattr(record, "context", None)
        if isinstance(context, Mapping):
            payload["context"] = {str(key): _sanitize(value) for key, value in context.items()}
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(log_dir: Path, level: str, retention_days: int) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_dir / "natureai-next.jsonl",
        when="midnight",
        backupCount=retention_days,
        encoding="utf-8",
        utc=True,
    )
    file_handler.setFormatter(JsonFormatter())
    root.addHandler(file_handler)


def _sanitize(value: object) -> object:
    if isinstance(value, Path):
        return value.name
    if isinstance(value, str) and ("\\" in value or "/" in value):
        return Path(value).name
    if isinstance(value, bool | int | float) or value is None:
        return value
    return str(value)
