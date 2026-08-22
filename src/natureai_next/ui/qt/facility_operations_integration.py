"""Runtime integration of facility planning into the existing V5 Operations page.

The V5 desktop module is intentionally kept stable: this module enhances the
already-created ``AssetEquipmentOperations`` instance instead of duplicating its
asset, maintenance or calibration logic.  The canonical Operations location
hierarchy and service remain authoritative.
"""
from __future__ import annotations

from pathlib import Path
from types import MethodType
from typing import Callable

from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QPushButton,
)

from natureai_next.application.facility_library import FacilityDrawingLibraryBridge
from natureai_next.ui.qt.facility_floorplan import FacilityFloorplanDialog
from natureai_next.ui.qt.facility_planning import FacilityPlanningWorkspace


def _button(page, text: str) -> QPushButton | None:
    return next((item for item in page.findChildren(QPushButton) if item.text() == text), None)


def _rewire(button: QPushButton | None, handler: Callable[[], None], *, text: str | None = None) -> None:
    if button is None:
        return
    try:
        button.clicked.disconnect()
    except (RuntimeError, TypeError):
        pass
    if text is not None:
        button.setText(text)
    button.clicked.connect(handler)


def _action_row(page, tab_title: str) -> QHBoxLayout | None:
    for index in range(page.tabs_widget.count()):
        if page.tabs_widget.tabText(index) != tab_title:
            continue
        tab = page.tabs_widget.widget(index)
        layout = tab.layout()
        if layout is None:
            return None
        for item_index in range(layout.count()):
            candidate = layout.itemAt(item_index).layout()
            if isinstance(candidate, QHBoxLayout):
                return candidate
    return None


def _main_window(page):
    candidate = page.parent()
    while candidate is not None:
        if hasattr(candidate, "_library_database_path"):
            return candidate
        candidate = candidate.parent() if hasattr(candidate, "parent") else None
    window = page.window() if hasattr(page, "window") else None
    return window if window is not page else None


def _library_bridge(page) -> FacilityDrawingLibraryBridge | None:
    window = _main_window(page)
    library_database = getattr(window, "_library_database_path", None) if window is not None else None
    if not library_database:
        QMessageBox.information(
            page,
            "Facility drawings",
            "The Fieldora Library database is not available in this workspace.",
        )
        return None
    return FacilityDrawingLibraryBridge(page.service, Path(library_database))


def _choose_library_drawing(page, title: str, *, svg_only: bool = False):
    bridge = _library_bridge(page)
    if bridge is None:
        return None, None
    assets = list(bridge.searchable_drawing_assets())
    if svg_only:
        assets = [asset for asset in assets if Path(asset.path).suffix.casefold() == ".svg"]
    if not assets:
        QMessageBox.information(
            page,
            title,
            "No suitable drawing asset is currently available in the Library. "
            "Import the drawing into Library first so the preserved source remains searchable and governed.",
        )
        return bridge, None
    labels = [f"{asset.title} · {asset.asset_type} · {Path(asset.path).name}" for asset in assets]
    choice, ok = QInputDialog.getItem(page, title, "Library asset", labels, 0, False)
    if not ok:
        return bridge, None
    return bridge, assets[labels.index(choice)]


def _selected_drawing(page) -> dict | None:
    return page._row_for_table(page.drawing_table)


def _open_drawing(page) -> None:
    row = _selected_drawing(page)
    if not row:
        QMessageBox.information(page, "Facility floorplan", "Select a drawing first.")
        return
    FacilityFloorplanDialog(
        page.service,
        actor=page.actor(),
        drawing_id=str(row["id"]),
        editable=page._allowed("update", "drawing"),
        parent=page,
    ).exec()
    page.refresh()


def _show_location(page, location_id: str | None) -> None:
    if not location_id:
        QMessageBox.information(page, "Location drawing", "This item has no current physical location.")
        return
    context = page.service.location_drawing_context(str(location_id), actor=page.actor(), include_planned=True)
    if context is None:
        QMessageBox.information(
            page,
            "Location drawing",
            "No current or planned floorplan is linked to this location or one of its parent locations yet.",
        )
        return
    FacilityFloorplanDialog(
        page.service,
        actor=page.actor(),
        drawing_id=str(context.get("id") or ""),
        location_id=str(location_id),
        editable=page._allowed("update", "drawing"),
        parent=page,
    ).exec()
    page.refresh()


def _show_asset_location(page) -> None:
    row = page._row_for_table(page.asset_table)
    if not row:
        QMessageBox.information(page, "Location drawing", "Select an asset first.")
        return
    _show_location(page, row.get("location_id"))


def _show_facility_location(page) -> None:
    row = page._row_for_table(page.location_table)
    if not row:
        QMessageBox.information(page, "Location drawing", "Select a facility/storage location first.")
        return
    _show_location(page, str(row.get("id") or ""))


def _add_drawing_from_library(page) -> None:
    bridge, asset = _choose_library_drawing(page, "Add facility drawing")
    if bridge is None or asset is None:
        return
    locations = list(page.service.locations(page.actor()))
    if not locations:
        QMessageBox.information(page, "Add facility drawing", "Create a facility/storage location first.")
        return
    labels = [page.service.location_path(row["id"], page.actor()) for row in locations]
    location_label, ok = QInputDialog.getItem(page, "Add facility drawing", "Drawing location", labels, 0, False)
    if not ok:
        return
    location_id = str(locations[labels.index(location_label)]["id"])
    title, ok = QInputDialog.getText(page, "Add facility drawing", "Title", text=asset.title)
    if not ok or not title.strip():
        return
    version, ok = QInputDialog.getText(page, "Add facility drawing", "Revision / version")
    if not ok:
        return
    status, ok = QInputDialog.getItem(
        page,
        "Add facility drawing",
        "Lifecycle state",
        ("draft", "planned", "approved", "scheduled", "current"),
        0,
        False,
    )
    if not ok:
        return
    extension = Path(asset.path).suffix.casefold()
    source_format = extension.lstrip(".") or "unknown"
    try:
        drawing_id = page.service.add_drawing(
            title.strip(),
            source_format,
            asset.path,
            page.actor(),
            location_id=location_id,
            version=version,
            status=status,
            library_asset_id=asset.asset_id,
            operational_svg_asset_id=asset.asset_id if extension == ".svg" else "",
            operational_svg_path=asset.path if extension == ".svg" else "",
        )
        bridge.link_source_asset(
            drawing_id,
            asset.asset_id,
            actor=page.actor(),
            relationship="design_source",
        )
    except Exception as exc:
        QMessageBox.warning(page, "Add facility drawing", str(exc))
        return
    page.refresh()


def _link_library_source(page) -> None:
    drawing = _selected_drawing(page)
    if not drawing:
        QMessageBox.information(page, "Drawing source", "Select a drawing revision first.")
        return
    bridge, asset = _choose_library_drawing(page, "Link drawing source")
    if bridge is None or asset is None:
        return
    relationship, ok = QInputDialog.getItem(
        page,
        "Link drawing source",
        "Relationship",
        (
            "reference",
            "architectural",
            "structural",
            "electrical",
            "fire_safety",
            "hvac",
            "storage_layout",
            "historical",
            "derived_from",
        ),
        0,
        False,
    )
    if not ok:
        return
    try:
        bridge.link_source_asset(
            str(drawing["id"]),
            asset.asset_id,
            actor=page.actor(),
            relationship=relationship,
        )
    except Exception as exc:
        QMessageBox.warning(page, "Drawing source", str(exc))
        return
    page.refresh()


def _set_library_svg(page) -> None:
    drawing = _selected_drawing(page)
    if not drawing:
        QMessageBox.information(page, "Operational SVG", "Select a drawing revision first.")
        return
    bridge, asset = _choose_library_drawing(page, "Operational floorplan SVG", svg_only=True)
    if bridge is None or asset is None:
        return
    try:
        bridge.set_operational_svg_asset(str(drawing["id"]), asset.asset_id, actor=page.actor())
    except Exception as exc:
        QMessageBox.warning(page, "Operational SVG", str(exc))
        return
    page.refresh()


def integrate_asset_equipment_operations(page) -> None:
    """Enhance one already-created V5 ``AssetEquipmentOperations`` page."""
    if getattr(page, "_facility_floorplan_integrated", False):
        return
    if not all(hasattr(page, name) for name in ("tabs_widget", "service", "asset_table", "location_table", "drawing_table")):
        return
    page._facility_floorplan_integrated = True

    def open_drawing(self):
        _open_drawing(self)

    def add_drawing(self):
        _add_drawing_from_library(self)

    def map_locations(self):
        _open_drawing(self)

    page._open_drawing = MethodType(open_drawing, page)
    page._add_drawing = MethodType(add_drawing, page)
    page._add_marker = MethodType(map_locations, page)

    _rewire(_button(page, "Open drawing"), page._open_drawing)
    _rewire(_button(page, "Add drawing"), page._add_drawing)
    _rewire(_button(page, "Place location code"), page._add_marker, text="Map locations on floorplan")

    extra_buttons: list[tuple[QPushButton, str, str, object | None]] = []

    asset_row = _action_row(page, "Equipment & assets")
    if asset_row is not None:
        button = QPushButton("Show location drawing")
        button.setObjectName("tool")
        button.clicked.connect(lambda: _show_asset_location(page))
        asset_row.insertWidget(max(0, asset_row.count() - 1), button)
        extra_buttons.append((button, "read", "drawing", page.asset_table))

    facility_row = _action_row(page, "Facilities & storage")
    if facility_row is not None:
        button = QPushButton("Show location drawing")
        button.setObjectName("tool")
        button.clicked.connect(lambda: _show_facility_location(page))
        facility_row.insertWidget(max(0, facility_row.count() - 1), button)
        extra_buttons.append((button, "read", "drawing", page.location_table))

    drawing_row = _action_row(page, "Building drawings")
    if drawing_row is not None:
        source_button = QPushButton("Link Library source")
        source_button.setObjectName("tool")
        source_button.clicked.connect(lambda: _link_library_source(page))
        drawing_row.insertWidget(max(0, drawing_row.count() - 1), source_button)
        extra_buttons.append((source_button, "update", "drawing", page.drawing_table))

        svg_button = QPushButton("Use Library SVG")
        svg_button.setObjectName("tool")
        svg_button.clicked.connect(lambda: _set_library_svg(page))
        drawing_row.insertWidget(max(0, drawing_row.count() - 1), svg_button)
        extra_buttons.append((svg_button, "update", "drawing", page.drawing_table))

    planning = FacilityPlanningWorkspace(page.db, page.tabs_widget)
    page.tabs_widget.addTab(planning, "Layouts & relocation")
    page._facility_planning_workspace = planning
    page._facility_extra_buttons = extra_buttons

    original_update_actions = page._update_actions

    def update_actions(self):
        original_update_actions()
        for button, action, kind, table in self._facility_extra_buttons:
            selected = True if table is None else bool(table.selectedItems())
            button.setEnabled(self._allowed(action, kind) and selected)

    page._update_actions = MethodType(update_actions, page)
    page._update_actions()
