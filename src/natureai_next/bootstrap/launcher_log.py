"""Minimal pre-GUI launcher diagnostics shared by windowless entry points."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from natureai_next.bootstrap.paths import resolve_application_paths


def write_launcher_log(filename: str, status: str, detail: str = "") -> None:
    log_dir = resolve_application_paths().logs_dir
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "status": status,
            "detail": detail,
        }
        with (log_dir / filename).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        pass
