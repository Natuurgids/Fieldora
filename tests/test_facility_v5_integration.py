from __future__ import annotations

import sys

import pytest

from natureai_next.ui.qt.navigation_contracts import validate_page_mapping, workspace_names


class _DummyPage:
    route_requested = object()

    def refresh(self) -> None:
        pass


def test_navigation_validation_stays_qt_lazy_for_release_tooling():
    pages = {name: _DummyPage() for name in workspace_names()}
    before = set(sys.modules)

    validate_page_mapping(pages)

    newly_loaded = set(sys.modules) - before
    assert "natureai_next.ui.qt.facility_operations_integration" not in newly_loaded


def test_facility_operations_integration_module_imports_when_gui_available():
    pytest.importorskip("PySide6")
    from natureai_next.ui.qt.facility_operations_integration import (
        integrate_asset_equipment_operations,
    )

    assert callable(integrate_asset_equipment_operations)
