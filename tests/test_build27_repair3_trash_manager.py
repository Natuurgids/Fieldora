from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_gallery_has_no_permanent_delete_control() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/library.py").read_text(encoding="utf-8")
    assert 'QPushButton("Delete permanently…")' not in source
    assert "selection_layout.addWidget(self._delete_selected)" not in source


def test_trash_manager_is_navigation_workspace() -> None:
    app = (ROOT / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    manager = (ROOT / "src/natureai_next/ui/qt/trash_manager.py").read_text(encoding="utf-8")
    assert '("Trash & Deletion Approvals", "Trash Manager")' in app
    assert "TrashManagerWorkspace" in app
    assert "WHERE a.lifecycle_state='trashed'" in manager
    assert "without gallery thumbnails or live layout churn" in manager
    assert "QThread" in manager
