from pathlib import Path


def test_installer_science_smoke_ignores_windows_temp_cleanup_lock() -> None:
    source = Path("scripts/verify_install.py").read_text(encoding="utf-8")
    assert 'prefix="fieldora-science-check-", ignore_cleanup_errors=True' in source
    assert "Qt.WidgetAttribute.WA_DeleteOnClose" in source


def test_science_workspace_unsubscribes_before_qt_child_destruction() -> None:
    source = Path("src/natureai_next/ui/qt/science.py").read_text(encoding="utf-8")
    close_event = source.index("def closeEvent(self, event: object)")
    unsubscribe = source.index("_unsubscribe_workspace_context", close_event)
    parent_close = source.index("super().closeEvent(event)", unsubscribe)
    assert close_event < unsubscribe < parent_close
