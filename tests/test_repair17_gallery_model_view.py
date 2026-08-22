from pathlib import Path


def test_photo_gallery_uses_virtualized_model_view() -> None:
    source = (
        Path(__file__).parents[1] / "src/natureai_next/ui/qt/library.py"
    ).read_text(encoding="utf-8")
    assert "class _GalleryModel(QAbstractListModel)" in source
    assert "class _GalleryDelegate(QStyledItemDelegate)" in source
    assert "self._grid = QListView()" in source
    assert "setUniformItemSizes(True)" in source
    assert "setLayoutMode(QListView.LayoutMode.Batched)" in source
    assert "beginInsertRows" in source
    assert "_schedule_visible_thumbnails" in source
    assert "self._thumbnail_queued" in source
    assert "QListWidgetItem" not in source
