"""Library lifecycle composition contracts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from natureai_next.domain.library import IntegrityReport, LibraryLayout, LibraryManifest


class OpenLibraryPort(Protocol):
    layout: LibraryLayout
    manifest: LibraryManifest
    connection_factory: object

    def integrity(self, *, full: bool = False) -> IntegrityReport: ...
    def backup_database(self, destination: Path) -> Path: ...
    def ensure_runtime_schema(self) -> None: ...
    def close(self) -> None: ...


class LibraryLifecycleBackend(Protocol):
    def create(
        self, root: Path, *, display_name: str, default_locale: str = "en"
    ) -> OpenLibraryPort: ...
    def open(self, root: Path) -> OpenLibraryPort: ...


LibraryBackendFactory = Callable[[object, object, object | None], LibraryLifecycleBackend]
_default_factory: LibraryBackendFactory | None = None


def configure_default_library_backend(factory: LibraryBackendFactory) -> None:
    global _default_factory
    _default_factory = factory


def default_library_backend() -> LibraryBackendFactory:
    if _default_factory is None:
        raise RuntimeError("Library lifecycle backend is not configured")
    return _default_factory
