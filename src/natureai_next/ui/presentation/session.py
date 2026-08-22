"""Versioned GUI session state with atomic JSON persistence."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SessionState:
    schema_version: int = 1
    workspace: str = "library"
    window_geometry_b64: str | None = None
    dock_state_b64: str | None = None
    grid_thumbnail_size: int = 192
    sort_mode: str = "capture_desc"
    inspector_visible: bool = True


class SessionStateStore:
    def load(self, path: Path) -> SessionState:
        if not path.exists():
            return SessionState()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schema_version") != 1:
                return SessionState()
            return SessionState(
                **{k: v for k, v in data.items() if k in SessionState.__dataclass_fields__}
            )
        except (OSError, ValueError, TypeError):
            return SessionState()

    def save(self, path: Path, state: SessionState) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                json.dump(asdict(state), f, sort_keys=True, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(name)
