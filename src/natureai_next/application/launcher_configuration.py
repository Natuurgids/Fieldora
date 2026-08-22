"""Shared desktop launcher configuration for Aperture and Maintenance Center."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def launcher_configuration_path() -> Path:
    configured = os.environ.get("APERTURE_DATA_ROOT") or os.environ.get("NATUREAI_DATA_ROOT")
    if configured:
        return Path(configured).expanduser().resolve() / "roaming" / "launcher.json"
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return root / "NatureAI" / "NatureAI Next" / "launcher.json"


def is_aperture_library(path: Path) -> bool:
    return (
        path.is_dir() and (path / "library.json").is_file() and (path / "library.sqlite3").is_file()
    )


@dataclass(frozen=True, slots=True)
class LauncherConfiguration:
    last_library: Path | None = None
    startup_behavior: str = "last"  # last | ask | fixed


class LauncherConfigurationStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or launcher_configuration_path()

    def load(self) -> LauncherConfiguration:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, TypeError):
            return LauncherConfiguration()
        if not isinstance(payload, dict):
            return LauncherConfiguration()
        raw = payload.get("last_library")
        library = Path(raw.strip()) if isinstance(raw, str) and raw.strip() else None
        behavior = str(payload.get("startup_behavior", "last"))
        if behavior not in {"last", "ask", "fixed"}:
            behavior = "last"
        return LauncherConfiguration(last_library=library, startup_behavior=behavior)

    def save(self, configuration: LauncherConfiguration) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 2,
            "last_library": str(configuration.last_library) if configuration.last_library else "",
            "startup_behavior": configuration.startup_behavior,
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def remember_library(self, library: Path) -> None:
        current = self.load()
        self.save(
            LauncherConfiguration(
                last_library=library.resolve(), startup_behavior=current.startup_behavior
            )
        )
