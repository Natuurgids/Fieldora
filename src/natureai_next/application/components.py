"""Persistent resource-component switches and lightweight diagnostics."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import RLock


@dataclass(frozen=True, slots=True)
class ComponentState:
    key: str
    enabled: bool
    available: bool
    detail: str


class ResourceComponentRegistry:
    """Keeps optional resources switchable without deleting installed data."""

    DEFAULTS = {"gbif": True, "bioclip": True}

    def __init__(self, path: Path | None = None) -> None:
        root = Path(os.getenv("LOCALAPPDATA", Path.home())) / "NatureAI" / "NatureAI Next"
        self.path = (path or root / "component-settings.json").expanduser().resolve()
        self._lock = RLock()

    def _load(self) -> dict[str, bool]:
        values = dict(self.DEFAULTS)
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            for key in values:
                if key in payload:
                    values[key] = bool(payload[key])
        except (FileNotFoundError, OSError, ValueError, TypeError):
            pass
        return values

    def enabled(self, key: str) -> bool:
        return self._load().get(key, False)

    def set_enabled(self, key: str, enabled: bool) -> None:
        if key not in self.DEFAULTS:
            raise KeyError(key)
        with self._lock:
            values = self._load()
            values[key] = bool(enabled)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(values, indent=2, sort_keys=True), encoding="utf-8")
            temporary.replace(self.path)
