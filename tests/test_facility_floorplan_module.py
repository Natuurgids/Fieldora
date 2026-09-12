from __future__ import annotations

import pytest


def test_facility_floorplan_module_imports_when_gui_available():
    pytest.importorskip("PySide6")
    from natureai_next.ui.qt.facility_floorplan import FacilityFloorplanDialog, FloorplanCanvas

    assert FacilityFloorplanDialog.__name__ == "FacilityFloorplanDialog"
    assert FloorplanCanvas.__name__ == "FloorplanCanvas"
