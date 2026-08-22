from pathlib import Path

SOURCE = Path('src/natureai_next/ui/qt/v5_desktop.py').read_text(encoding='utf-8')


def test_research_map_toolbar_is_map_specific():
    research = SOURCE[SOURCE.index('class Research(Page):'):SOURCE.index('class MeasurementsSampling(Page):')]
    header = research[research.index("top=QHBoxLayout()") : research.index("side=QFrame()")]
    assert "Open full map" in header
    assert "Measurements & samples" not in header
    assert "Data quality" not in header
    assert "Surveys & sampling" not in header


def test_project_map_resolves_stored_map_before_full_map_fallback():
    preview = SOURCE[SOURCE.index('class ProjectMapPreview(QWidget):'):SOURCE.index('class Page(QWidget):')]
    assert "SELECT image_path FROM pm_project_map_snapshots" in preview
    assert "Project stored map" in preview
    assert "Installed OpenStreetMap/offline basemap available in Full Map" in preview
    assert "activate_requested=Signal()" in preview
    assert "mouseDoubleClickEvent" in preview


def test_full_map_route_keeps_project_context():
    application = Path('src/natureai_next/ui/qt/application.py').read_text(encoding='utf-8')
    assert 'if prefix == "__project_map__:"' in application
    assert 'self._map_workspace.select_project(identity)' in application
