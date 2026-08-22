"""Low-overhead startup timing diagnostics for Aperture."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from natureai_next.bootstrap.paths import resolve_application_paths


@dataclass
class StartupTimeline:
    started_at: float = field(default_factory=time.perf_counter)
    events: list[dict[str, object]] = field(default_factory=list)

    def mark(self, stage: str, **detail: object) -> float:
        elapsed_ms = round((time.perf_counter() - self.started_at) * 1000, 1)
        event: dict[str, object] = {"stage": stage, "elapsed_ms": elapsed_ms}
        if detail:
            event["detail"] = detail
        self.events.append(event)
        return elapsed_ms

    def write(self, *, library: str | None = None) -> Path | None:
        try:
            root = resolve_application_paths().logs_dir
            root.mkdir(parents=True, exist_ok=True)
            target = root / "startup-timing.jsonl"
            payload = {
                "timestamp_utc": datetime.now(UTC).isoformat(),
                "library": library,
                "events": self.events,
            }
            with target.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
            return target
        except OSError:
            return None


def latest_startup_summary(path: Path | None = None) -> dict[str, object] | None:
    """Return the newest valid startup record without failing maintenance UI startup."""
    target = path or (resolve_application_paths().logs_dir / "startup-timing.jsonl")
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and isinstance(value.get("events"), list):
            return value
    return None
