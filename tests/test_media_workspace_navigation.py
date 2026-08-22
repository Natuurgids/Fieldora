from pathlib import Path


def test_desktop_exposes_independent_media_workspaces() -> None:
    source = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert all(f'"{name}"' in source for name in ("Photos", "Sounds", "Videos", "Documents"))
    assert "capabilities_changed.connect(" in source
    assert "self._refresh_library_type_navigation" in source
    assert "self._sounds_workspace = MediaLibraryWorkspace" in source
    assert "self._videos_workspace = MediaLibraryWorkspace" in source
    assert "self._documents_workspace = MediaLibraryWorkspace" in source


def test_media_workspaces_have_type_specific_metadata() -> None:
    source = Path("src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    query_source = Path("src/natureai_next/application/media_queries.py").read_text(
        encoding="utf-8"
    )
    for expected in (
        "sample_rate_hz",
        "microphone",
        "frame_rate",
        "video_codec",
        "page_count",
        "language_code",
    ):
        assert expected in source
    assert "QAbstractTableModel" in source
    assert "QThread" in source
    assert "PRAGMA query_only=ON" in query_source
