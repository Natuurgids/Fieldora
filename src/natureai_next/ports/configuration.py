"""Application-owned configuration persistence contract."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol


class ConfigurationStore(Protocol):
    """Persist versioned settings without exposing a file format to Application."""

    def read(self, path: Path) -> dict[str, object]: ...

    def write(self, path: Path, document: Mapping[str, object]) -> None: ...

    def backup(self, path: Path, suffix: str) -> Path | None: ...
