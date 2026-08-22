from __future__ import annotations

from pathlib import Path

import pytest

from natureai_next.application.library_service import LibraryService
from natureai_next.infrastructure.diagnostics.system_services import (
    SystemClock,
    SystemUuidGenerator,
)
from natureai_next.infrastructure.library_lifecycle import SqliteLibraryLifecycleBackend


def _service():
    return LibraryService(
        SystemClock(),
        SystemUuidGenerator(),
        backend_factory=lambda c, i, s: SqliteLibraryLifecycleBackend(c, i, s),
    )


def test_open_or_create_clean_initializes_empty_selected_directory(tmp_path: Path) -> None:
    root = tmp_path / "Library"
    root.mkdir()
    opened = _service().open_or_create_clean(root)
    opened.close()
    assert (root / "library.json").is_file()
    assert (root / "library.sqlite3").is_file()
    assert not list(tmp_path.glob(".*.aperture-staging-*"))


def test_open_or_create_clean_refuses_nonempty_nonlibrary(tmp_path: Path) -> None:
    root = tmp_path / "Not A Library"
    root.mkdir()
    marker = root / "keep.txt"
    marker.write_text("keep")
    with pytest.raises(FileExistsError):
        _service().open_or_create_clean(root)
    assert marker.read_text() == "keep"


def test_existing_invalid_library_is_not_replaced(tmp_path: Path) -> None:
    root = tmp_path / "Legacy"
    root.mkdir()
    (root / "library.json").write_text("legacy")
    (root / "library.sqlite3").write_bytes(b"legacy")
    with pytest.raises((ValueError, Exception)):
        _service().open_or_create_clean(root)
    assert (root / "library.json").read_text() == "legacy"
    assert (root / "library.sqlite3").read_bytes() == b"legacy"
