"""Application facade for the non-destructive library lifecycle."""

from __future__ import annotations

from pathlib import Path

from natureai_next.ports.clock import Clock
from natureai_next.ports.identity import UuidGenerator
from natureai_next.ports.library_lifecycle import (
    LibraryBackendFactory,
    OpenLibraryPort,
    default_library_backend,
)

OpenLibrary = OpenLibraryPort


class LibraryService:
    def __init__(
        self,
        clock: Clock,
        ids: UuidGenerator,
        settings: object | None = None,
        *,
        backend_factory: LibraryBackendFactory | None = None,
    ) -> None:
        self._backend = (backend_factory or default_library_backend())(clock, ids, settings)

    def create(
        self, root: Path, *, display_name: str, default_locale: str = "en"
    ) -> OpenLibraryPort:
        return self._backend.create(root, display_name=display_name, default_locale=default_locale)

    def open(self, root: Path) -> OpenLibraryPort:
        return self._backend.open(root)

    def open_or_create_clean(
        self, root: Path, *, display_name: str = "Aperture Library", default_locale: str = "en"
    ) -> OpenLibraryPort:
        """Create only when the selected path is absent or empty; otherwise open strictly.

        Existing library artifacts are never deleted, moved, migrated, or replaced by normal startup.
        """
        root = root.expanduser().resolve()
        if root.exists():
            if not root.is_dir():
                raise NotADirectoryError(f"library path is not a directory: {root}")
            if any(root.iterdir()):
                if not ((root / "library.json").exists() or (root / "library.sqlite3").exists()):
                    raise FileExistsError(
                        f"selected library directory is not empty and is not an Aperture library: {root}"
                    )
                return self.open(root)
        return self.create(root, display_name=display_name, default_locale=default_locale)
