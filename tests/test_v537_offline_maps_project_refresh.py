from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
V5 = (ROOT / "src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")


def test_library_exposes_offline_maps_workspace():
    library = V5[V5.index("class Library(Page):"):V5.index("class Observations(Page):")]
    assert "('Maps & project areas','Map')" in library
    assert "('Offline map packages','Offline Maps')" in library
    assert '"Offline Maps",' in APP
    assert "self._stack.addWidget(self._offline_maps_resources_workspace)" in APP


def test_research_map_route_opens_drawing_workspace_with_project_context():
    maps = (ROOT / "src/natureai_next/ui/qt/maps.py").read_text(encoding="utf-8")
    context = APP[APP.index('if prefix.startswith("__project_")'):APP.index("with sqlite3.connect(self._library_database_path)", APP.index('if prefix.startswith("__project_")'))]
    assert 'self._select_workspace("Map")' in context
    assert "self._map_workspace.select_project(identity)" in context
    assert "def select_project(self, project_id: str)" in maps
    assert "project.project_id == self._active_project_id" in maps
    for label in ("Draw Project Area", "Undo Point", "Finish & Attach…", "Clear Area", "Save Project Snapshot…"):
        assert label in maps


def test_v5_pages_refresh_on_direct_sidebar_activation():
    clicked = APP[APP.index("def _workspace_item_clicked"):APP.index("def open_knowledge_center")]
    assert 'self._v5_pages[name].refresh()' in clicked
    assert clicked.index('self._v5_pages[name].refresh()') < clicked.index('self._stack.setCurrentWidget(target)')


def test_project_refresh_preserves_live_combo_selection_and_requeries_database():
    research = V5[V5.index("class Research(Page):"):V5.index("class DataTable(QTableWidget):")]
    assert "self.combo.currentData() or QSettings().value('v5/active_project_id','')" in research
    assert "SELECT project_id,name,status FROM pm_projects ORDER BY updated_at_us DESC" in research
