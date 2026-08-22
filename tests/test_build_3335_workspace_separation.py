from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = (ROOT / "src/natureai_next/ui/qt/library.py").read_text(encoding="utf-8")
APPLICATION = (ROOT / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")


def test_workspace_splitters_have_independent_names_and_keys() -> None:
    assert "libraryMainSplitter" in LIBRARY
    assert "collectionsMainSplitter" in LIBRARY
    assert "ui/library/main_splitter" in LIBRARY
    assert "ui/collections/main_splitter" in LIBRARY


def test_workspace_lifecycle_does_not_reconstruct_views() -> None:
    assert "def activate(self)" in LIBRARY
    assert "def deactivate(self)" in LIBRARY
    assert "setCurrentWidget(target)" in APPLICATION
    assert "target.activate()" in APPLICATION


def test_refresh_has_recursion_guard() -> None:
    refresh = LIBRARY[LIBRARY.index("def refresh(self)"):LIBRARY.index("def load_more(self)")]
    assert "if self._refreshing:" not in refresh
    assert "self._page_request_id += 1" in refresh
    assert "self._refreshing = True" in LIBRARY
    assert LIBRARY.count("self._refreshing = False") >= 3


def test_inspector_is_scrollable_and_bounded() -> None:
    assert "inspector_scroll.setWidgetResizable(True)" in LIBRARY
    assert "inspector_scroll.setMinimumWidth(260)" in LIBRARY
    assert "inspector_scroll.setMaximumWidth(410)" in LIBRARY


def test_long_paths_and_editors_do_not_force_inspector_width() -> None:
    assert 'replace("\\\\", "\\\\&#8203;")' in LIBRARY
    assert "control.setMinimumWidth(0)" in LIBRARY
    assert "QSizePolicy.Policy.Ignored" in LIBRARY
    assert "QFormLayout.RowWrapPolicy.WrapLongRows" in LIBRARY


def test_collections_manager_is_bounded_before_async_load() -> None:
    assert "organize_drawer.setMinimumWidth(240)" in LIBRARY
    assert "organize_drawer.setMaximumWidth(380)" in LIBRARY
    assert "collection_manager_controls" in LIBRARY
    assert "def _constrain_splitter_to_viewport(self)" in LIBRARY
    assert "QTimer.singleShot(0, self._constrain_splitter_to_viewport)" in LIBRARY
