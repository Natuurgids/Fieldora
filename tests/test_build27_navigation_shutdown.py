from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src/natureai_next/ui/qt/application.py"


def test_build27_navigation_groups_and_labels_are_declared():
    source = APP.read_text(encoding="utf-8")
    for label in (
        '"Science Workspace"', '"Platform Management"',
        '"Library Administration"', '"AI & Processing"',
        '("Import", "Imports")', '("Habitats & Seasonality", "Conservation & Seasonality")',
        '("Enabled Modules", "Library Types")',
        '("Installed Integrations & API Connections", "Integrations")',
    ):
        assert label in source


def test_build27_menu_bar_and_shutdown_are_task_oriented():
    source = APP.read_text(encoding="utf-8")
    for menu in ('addMenu("&File")', 'addMenu("&Research")', 'addMenu("&Data")',
                 'addMenu("&Analyse")', 'addMenu("&Collaborate")',
                 'addMenu("&Platform")', 'addMenu("&Help")'):
        assert menu in source
    assert 'addMenu("&About Fieldora")' not in source
    assert 'QAction("Shutdown", self)' in source
    assert 'QAction("Quit", self)' not in source
    assert 'def _show_shutdown_progress' in source
    assert '"Shutdown complete."' in source
