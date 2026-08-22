from natureai_next.ui.enrichment.interaction import build_overlay_scene


def test_spatial_scene_supports_box_and_polygon_hit_testing():
    scene = build_overlay_scene(
        "enr-1",
        {
            "kind": "spatial",
            "boxes": ({"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},),
            "polygons": (((0.6, 0.1), (0.9, 0.1), (0.75, 0.5)),),
        },
    )
    assert scene.hit_test(0.2, 0.3).kind == "box"
    assert scene.hit_test(0.75, 0.2).kind == "polygon"
    assert scene.hit_test(0.02, 0.02) is None


def test_timeline_scene_normalizes_against_media_duration_and_selects_by_time():
    scene = build_overlay_scene(
        "enr-2",
        {"kind": "timeline", "start_seconds": 10, "end_seconds": 20},
        duration_seconds=100,
    )
    region = scene.regions[0]
    assert region.x == 0.1
    assert region.width == 0.1
    assert scene.region_at_time(15) == region
    assert scene.region_at_time(25) is None


def test_time_frequency_scene_maps_frequency_to_vertical_coordinates():
    scene = build_overlay_scene(
        "enr-3",
        {
            "kind": "time-frequency",
            "start_seconds": 2,
            "end_seconds": 4,
            "low_hz": 1000,
            "high_hz": 5000,
        },
        duration_seconds=10,
        maximum_hz=10000,
    )
    region = scene.regions[0]
    assert region.x == 0.2
    assert region.width == 0.2
    assert region.y == 0.5
    assert region.height == 0.4
    assert region.contains(0.3, 0.7)
    assert not region.contains(0.3, 0.2)


def test_document_region_uses_same_normalized_selection_contract():
    scene = build_overlay_scene(
        "enr-4",
        {"kind": "document-region", "box": {"x": 0.25, "y": 0.1, "width": 0.5, "height": 0.2}},
    )
    assert scene.hit_test(0.5, 0.2).kind == "document-region"


def test_qt_panel_source_exposes_canvas_selection_and_playback_contract():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "src/natureai_next/ui/qt/enrichment.py").read_text(encoding="utf-8")
    assert "class CanonicalOverlayCanvas" in source
    assert "visualization_region_selected = Signal(str, str)" in source
    assert "visualization_time_selected = Signal(str, float)" in source
    assert "def set_playback_position" in source
    assert "build_overlay_scene(item.enrichment_id, item.visualization)" in source
