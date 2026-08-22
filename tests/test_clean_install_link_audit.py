from pathlib import Path


def test_research_map_actions_are_context_specific():
    desktop = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    research = desktop[desktop.index("class Research(Page):"):desktop.index("class MeasurementsSampling(Page):")]
    map_header = research[research.index("top=QHBoxLayout()"):research.index("side=QFrame()")]
    assert "__project_map__" in map_header
    assert "__project_measurements__" not in map_header
    assert "__project_surveys__" not in map_header
    assert "__project_quality__" not in map_header


def test_project_list_is_permission_filtered():
    project = Path("src/natureai_next/ui/qt/project_management.py").read_text(encoding="utf-8")
    refresh = project[project.index("    def refresh(self) -> None:"):project.index("    def refresh_project", project.index("    def refresh(self) -> None:"))]
    assert "self._context.accessible_projects" in refresh
    assert "self._service.projects()" not in refresh


def test_unknown_routes_fail_visibly_and_strict_mode_raises():
    app = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert "No workspace is registered for route" in app
    assert "FIELDORA_STRICT_ROUTES" in app
    assert "raise LookupError(message)" in app


def test_operational_inputs_use_governed_catalogues():
    desktop = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    assert "'custody_action'" in desktop
    assert "'laboratory_record_type'" in desktop
    assert "list_domain('parties')" in desktop
    assert "list_domain('laboratories')" in desktop
    assert "list_domain('templates')" in desktop
    assert "Specimen identifier'" not in desktop


def test_no_obsolete_measurement_tab_state_or_compatibility_markers():
    project = Path("src/natureai_next/ui/qt/project_management.py").read_text(encoding="utf-8")
    desktop = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    assert "_measurements_tab_index" not in project
    assert "Compatibility route retained" not in desktop
    assert "Legacy startup signature retained" not in desktop
