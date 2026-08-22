from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_research_preview_does_not_double_project_snapshot_polygon() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    assert "pts=[] if not self.pix.isNull() else" in source


def test_full_vector_map_can_restore_and_fit_project_polygon() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/vector_map_view.py").read_text(encoding="utf-8")
    assert "window.apertureSetProjectArea" in source
    assert "map.fitBounds(bounds" in source
    assert "view.aperture_set_project_area = set_project_area" in source


def test_map_workspace_loads_latest_selected_project_area() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/maps.py").read_text(encoding="utf-8")
    assert "ProjectManagementService(self._project_database_path).research_areas" in source
    assert 'getattr(self._vector_view, "aperture_set_project_area", None)' in source
    assert "self.refresh(auto_center=False)" in source


def test_legacy_project_area_canvas_fits_local_boundary() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/project_management.py").read_text(encoding="utf-8")
    assert "def _fit_research_area" in source
    assert "padding = max(extent * 0.12, 0.002)" in source
    assert "self.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)" in source


def test_project_research_page_displays_saved_streetmaps_snapshot() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/project_management.py").read_text(encoding="utf-8")
    assert "class StreetMapsSnapshotView" in source
    assert 'self._research_views.addTab(self._snapshot_view, "StreetMaps snapshot")' in source
    assert "self._map_snapshots.setCurrentRow(0)" in source
    assert "self._research_views.setCurrentWidget(self._snapshot_view)" in source
