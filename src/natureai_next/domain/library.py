"""Stable Library lifecycle value objects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LibraryLayout:
    root: Path
    database: Path
    manifest: Path
    managed_originals: Path
    sidecars: Path
    thumbnails: Path
    previews: Path
    vector_indexes: Path
    backups: Path
    temp: Path
    lock_file: Path

    @classmethod
    def at(cls, root: Path) -> LibraryLayout:
        resolved = root.expanduser().resolve()
        return cls(
            resolved,
            resolved / "library.sqlite3",
            resolved / "library.json",
            resolved / "originals",
            resolved / "sidecars",
            resolved / "cache" / "thumbnails",
            resolved / "cache" / "previews",
            resolved / "indexes" / "vectors",
            resolved / "backups",
            resolved / "temp",
            resolved / ".natureai-next.lock",
        )

    def create_directories(self) -> None:
        for path in (
            self.root,
            self.managed_originals,
            self.sidecars,
            self.thumbnails,
            self.previews,
            self.vector_indexes,
            self.backups,
            self.temp,
        ):
            path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class LibraryManifest:
    format_version: int
    library_public_id: str
    display_name: str
    created_at_us: int
    database_filename: str = "library.sqlite3"


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    quick_check: tuple[str, ...]
    foreign_key_violations: tuple[tuple[object, ...], ...]

    @property
    def healthy(self) -> bool:
        return self.quick_check == ("ok",) and not self.foreign_key_violations
