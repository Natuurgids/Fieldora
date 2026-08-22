from pathlib import Path

from natureai_next.ui.qt.vector_map_view import vector_map_html


def test_vector_document_restores_overlays_after_offline_style_lifecycle():
    asset_root = Path(__file__).parents[1] / "src/natureai_next/resources/map_renderer"
    html = vector_map_html("package-1", asset_root)
    assert "apertureScheduleOverlayRestore" in html
    assert "map.on('style.load'" in html
    assert "map.moveLayer(id)" in html
    assert "map.setLayoutProperty(layer.id,'visibility','visible')" in html
    assert "apertureOverlayDiagnostics" in html


def test_qt_adapter_retains_and_replays_preload_overlay_payload():
    source = (Path(__file__).parents[1] / "src/natureai_next/ui/qt/vector_map_view.py").read_text()
    assert "latest_overlay_payload" in source
    assert "view.loadFinished.connect(page_loaded)" in source
    assert "QTimer.singleShot(500, apply_latest_overlays)" in source
    assert "nonlocal latest_overlay_payload" in source
