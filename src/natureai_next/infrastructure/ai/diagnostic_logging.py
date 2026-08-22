"""User-controlled NatureAI inference diagnostics stored under the configured data root."""

from __future__ import annotations

import json
import os
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def data_root() -> Path:
    configured = os.environ.get("APERTURE_DATA_ROOT") or os.environ.get("NATUREAI_DATA_ROOT")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else (Path.cwd() / "ApertureData").resolve()
    )


def settings_path() -> Path:
    return data_root() / "config" / "diagnostics.json"


@dataclass(frozen=True, slots=True)
class DiagnosticSettings:
    enabled: bool = True
    level: str = "standard"
    max_bytes: int = 20 * 1024 * 1024


def load_settings() -> DiagnosticSettings:
    path = settings_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        level = str(payload.get("level", "standard")).lower()
        if level not in {"errors", "standard", "detailed"}:
            level = "standard"
        return DiagnosticSettings(
            bool(payload.get("enabled", True)),
            level,
            max(1_048_576, int(payload.get("max_bytes", 20 * 1024 * 1024))),
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return DiagnosticSettings()


def save_settings(settings: DiagnosticSettings) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(
            {"enabled": settings.enabled, "level": settings.level, "max_bytes": settings.max_bytes},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temp.replace(path)


def log_path() -> Path:
    return data_root() / "logs" / "natureai" / "natureai-inference.jsonl"


def _rotate(path: Path, max_bytes: int) -> None:
    try:
        if path.stat().st_size < max_bytes:
            return
    except OSError:
        return
    backup = path.with_suffix(path.suffix + ".1")
    try:
        backup.unlink(missing_ok=True)
        path.replace(backup)
    except OSError:
        pass


def write_event(event: str, *, level: str = "standard", **fields: Any) -> None:
    settings = load_settings()
    if not settings.enabled:
        return
    order = {"errors": 0, "standard": 1, "detailed": 2}
    if order.get(level, 1) > order.get(settings.level, 1):
        return
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate(path, settings.max_bytes)
    payload = {"timestamp_utc": datetime.now(UTC).isoformat(), "event": event, **fields}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True) + "\n")


def write_exception(
    event: str, exc: BaseException, *, detailed_fields: dict[str, Any] | None = None, **fields: Any
) -> None:
    settings = load_settings()
    base = {**fields, "exception_type": type(exc).__name__, "message": str(exc)}
    if settings.level == "detailed":
        base["traceback"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        if detailed_fields:
            base.update(detailed_fields)
    write_event(event, level="errors", **base)
