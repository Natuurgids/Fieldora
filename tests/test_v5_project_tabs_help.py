from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_research_overview_selects_live_project_and_renders_saved_or_vector_map():
    source = (ROOT / "src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    assert "self.combo=QComboBox()" in source
    assert "v5/active_project_id" in source
    assert "FROM pm_projects" in source
    assert "FROM pm_project_map_snapshots" in source
    assert "FROM pm_research_areas" in source
    assert "ProjectMapPreview" in source


def test_v5_tabs_route_to_real_workspaces_and_cards_are_responsive():
    source = (ROOT / "src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    routes = (ROOT / "src/natureai_next/ui/qt/v5_icons.py").read_text(encoding="utf-8")
    for route in ("Collections", "Trash Manager", "Observation History", "AI Review", "Knowledge Base", "Taxonomy", "Models"):
        assert route in source or route in routes
    assert "width>=1320 else 3 if width>=950 else 2 if width>=620 else 1" in source
    assert "height=116" in source
    assert "heading.setWordWrap(False)" in source
    assert "QSizePolicy.Policy.MinimumExpanding" in source


def test_help_and_guides_is_a_first_class_v5_workspace():
    pages = (ROOT / "src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    shell = (ROOT / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert "class Help(Page)" in pages
    assert '"Help & Guides": Help(parent)' in pages
    for topic in ("quick-start", "import", "ai-review", "offline-maps", "taxonomy", "troubleshooting", "__shortcuts__"):
        assert topic in pages
    assert '("Help & Guides","Help & Guides")' in shell
    assert 'name.startswith("__help_topic__:")' in shell
    assert "self.open_keyboard_shortcuts()" in shell


def test_v5_uses_isolated_clean_install_identity():
    installer = (ROOT / "scripts/install_windows.ps1").read_text(encoding="utf-8")
    paths = (ROOT / "src/natureai_next/bootstrap/paths.py").read_text(encoding="utf-8")
    assert "[string]$EnvironmentName = 'fieldora-v5'" in installer
    assert "FieldoraData-V5" in installer
    assert "Fieldora-Library-V5" in installer
    assert "Uninstall\\Fieldora V5" in installer
    assert "Programs\\Fieldora V5" in installer
    assert '_APP_NAME = "Fieldora V5"' in paths


def test_release_manifest_excludes_pytest_temporary_trees():
    manifest = (ROOT / "scripts/release_manifest.py").read_text(encoding="utf-8")
    assert '"pytest-of-root"' in manifest
