from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_photo_viewer_receives_shared_enrichment_controller() -> None:
    application = (ROOT / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert "enrichment_controller=self._enrichment_controller" in application


def test_viewer_projects_normalized_regions_in_pixmap_coordinates() -> None:
    viewer = (ROOT / "src/natureai_next/ui/qt/viewer.py").read_text(encoding="utf-8")
    assert "class ZoomableImageView" in viewer
    assert "set_overlay_scene" in viewer
    assert "_render_overlay_scene" in viewer
    assert "QGraphicsPolygonItem" in viewer
    assert "QGraphicsRectItem" in viewer
    assert "x * width" in viewer
    assert "y * height" in viewer


def test_async_preview_retains_scene_until_pixmap_arrives() -> None:
    viewer = (ROOT / "src/natureai_next/ui/qt/viewer.py").read_text(encoding="utf-8")
    assert "self._overlay_scene = scene" in viewer
    set_image = viewer.split("def set_image", 1)[1].split("def clear_image", 1)[0]
    assert "self._render_overlay_scene()" in set_image


def test_selection_is_bidirectional_between_image_and_canonical_panel() -> None:
    viewer = (ROOT / "src/natureai_next/ui/qt/viewer.py").read_text(encoding="utf-8")
    enrichment = (ROOT / "src/natureai_next/ui/qt/enrichment.py").read_text(encoding="utf-8")
    assert "overlay_region_selected" in viewer
    assert "select_visualization_region" in viewer
    assert "overlay_scene_changed" in enrichment
    assert "def select_region" in enrichment
