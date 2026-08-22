from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
V5 = (ROOT / "src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
ACCESSIBILITY = (ROOT / "src/natureai_next/ui/qt/accessibility.py").read_text(encoding="utf-8")


def test_global_shortcuts_are_hosted_by_the_visible_main_window():
    for attribute in (
        "_import_action",
        "_export_action",
        "_backup_action",
        "_restore_action",
        "_shutdown_action",
        "_shortcuts_action",
        "_context_help_action",
    ):
        assert f"self.addAction(self.{attribute})" in APP
    assert APP.count("Qt.ShortcutContext.ApplicationShortcut") >= 7


def test_documented_application_shortcuts_match_live_actions():
    expected = {
        "Ctrl+I": "Import folder",
        "Ctrl+E": "Open export",
        "Ctrl+Shift+B": "Back up library",
        "Ctrl+Shift+R": "Restore library",
        "F1": "Open context help",
        "Ctrl+/": "Open keyboard shortcuts",
        "Ctrl+Q": "Shutdown",
    }
    for shortcut, label in expected.items():
        assert f'QKeySequence("{shortcut}")' in APP
        assert f'("{label}", "{shortcut}", "Application")' in ACCESSIBILITY


def test_v5_administration_exposes_real_lifecycle_and_visibility_routes():
    for title, route in (
        ("Back up library", "__backup__"),
        ("Restore library", "__restore__"),
        ("Operations Center", "Activity Center"),
        ("Screens & modules", "Library Types"),
        ("AI & source switches", "Resource Components"),
    ):
        assert title in V5
        assert route in V5
    assert 'route == "__backup__"' in APP
    assert 'route == "__restore__"' in APP
