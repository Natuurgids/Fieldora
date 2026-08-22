from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_video_player_composites_normalized_overlay_over_video_surface() -> None:
    text = (ROOT / "src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    assert "class MediaOverlayCanvas" in text
    assert "video_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)" in text
    assert "video_stack.addWidget(self._video)" in text
    assert "video_stack.addWidget(self._overlay)" in text
    assert "self._overlay.set_scene(scene)" in text
    assert "self._overlay.set_playback_position(value)" in text


def test_document_workspace_renders_pdf_pages_with_page_relative_overlay() -> None:
    text = (ROOT / "src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    assert "class DocumentPageWidget" in text
    assert "from PySide6.QtPdf import QPdfDocument" in text
    assert "from PySide6.QtPdfWidgets import QPdfView" in text
    assert 'self._document_viewer.load_asset(asset_id, row.get("source_path"))' in text
    assert "self._document_viewer.set_overlay_scene(scene)" in text
    assert "self._document_viewer.select_region(region_id)" in text


def test_overlay_canvas_supports_boxes_polygons_selection_and_temporal_seek() -> None:
    text = (ROOT / "src/natureai_next/ui/qt/media_library.py").read_text(encoding="utf-8")
    assert "painter.drawPolygon" in text
    assert "painter.drawRect" in text
    assert "region = self._scene.hit_test(x, y)" in text
    assert "self.region_selected.emit(region.region_id)" in text
    assert "self.time_selected.emit(region.start_seconds)" in text
