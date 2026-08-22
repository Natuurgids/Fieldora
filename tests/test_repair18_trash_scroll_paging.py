from pathlib import Path


def test_trash_removes_model_rows_without_full_refresh() -> None:
    source = (
        Path(__file__).parents[1] / "src/natureai_next/ui/qt/library.py"
    ).read_text(encoding="utf-8")
    assert "def remove_public_ids" in source
    completed = source.split("def _maintenance_completed", 1)[1].split("def _maintenance_failed", 1)[0]
    assert "remove_public_ids" in completed
    assert "self.refresh()" not in completed
    assert "beginRemoveRows" in source


def test_gallery_scroll_triggers_guarded_paging() -> None:
    source = (
        Path(__file__).parents[1] / "src/natureai_next/ui/qt/library.py"
    ).read_text(encoding="utf-8")
    assert "valueChanged.connect(self._gallery_scrolled)" in source
    assert "def _load_more_if_needed" in source
    assert "if self._refreshing or self._next_cursor is None" in source
    assert "QTimer.singleShot(0, self._load_more_if_needed)" in source
