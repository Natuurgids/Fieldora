from pathlib import Path


def test_project_specialist_tabs_are_wired_to_research_operations():
    project = Path("src/natureai_next/ui/qt/project_management.py").read_text(encoding="utf-8")
    science = Path("src/natureai_next/ui/qt/science.py").read_text(encoding="utf-8")
    application = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")

    assert "route_requested = Signal(str)" in project
    assert "openResearchOperations" in project
    assert '"Survey events": "__project_surveys__:"' in project
    assert '"Samples": "__project_measurements__:"' in project
    assert '"Data quality": "__project_quality__:"' in project
    assert "self._project_management.route_requested.connect(self.route_requested.emit)" in science
    assert "workspace.route_requested.connect(self._select_workspace)" in application


def test_legacy_project_tabs_do_not_duplicate_research_mutation_buttons():
    project = Path("src/natureai_next/ui/qt/project_management.py").read_text(encoding="utf-8")
    surveys = project[project.index("def _build_surveys_page"):project.index("def _build_measurements_page")]
    quality = project[project.index("def _build_quality_page"):project.index("def _build_research_area_page")]
    assert "New protocol" not in surveys
    assert "Record detection" not in surveys
    assert "Run quality checks" not in quality
    assert "Dismiss selected" not in quality
