"""Persistent, append-only update history for support and diagnostics."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class UpdateHistoryEntry:
    version: str
    status: str
    detail: str = ""
    created_at_utc: str = ""

    def normalized(self) -> UpdateHistoryEntry:
        return UpdateHistoryEntry(
            version=self.version,
            status=self.status,
            detail=self.detail,
            created_at_utc=self.created_at_utc or datetime.now(UTC).isoformat(),
        )


class UpdateHistoryStore:
    """Store update outcomes as JSON lines without changing the library schema."""

    def append(self, path: Path, entry: UpdateHistoryEntry) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = entry.normalized()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(normalized), sort_keys=True) + "\n")

    def load(self, path: Path, *, limit: int = 50) -> tuple[UpdateHistoryEntry, ...]:
        if not path.is_file():
            return ()
        entries: list[UpdateHistoryEntry] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                entries.append(
                    UpdateHistoryEntry(
                        version=str(payload.get("version", "")),
                        status=str(payload.get("status", "unknown")),
                        detail=str(payload.get("detail", "")),
                        created_at_utc=str(payload.get("created_at_utc", "")),
                    )
                )
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
        return tuple(entries[-max(1, limit) :][::-1])
