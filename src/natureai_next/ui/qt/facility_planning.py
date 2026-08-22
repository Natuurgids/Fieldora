"""Future facility layouts and physical relocation execution for Operations.

This widget is deliberately domain-neutral.  Museums, laboratories, archives,
warehouses and other installations use the same canonical location hierarchy;
domain packs may add their own vocabulary and validation rules around it.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from natureai_next.application.facility_planning import FacilityPlanningService
from natureai_next.ui.qt.facility_floorplan import FacilityFloorplanDialog


_FINAL_STATES = ("stored", "placed", "displayed", "completed")


class FacilityPlanningWorkspace(QWidget):
    """Versioned floorplans, future layouts, picklists and relocation progress."""

    def __init__(self, database_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.database_path = Path(database_path)
        self.service = FacilityPlanningService(self.database_path)
        self.actor = lambda: os.environ.get("FIELDORA_IDENTITY_ID", "local-user")
        self._plans: list[dict] = []
        self._campaigns: list[dict] = []
        self._placements: list[dict] = []
        self._steps: list[dict] = []

        outer = QVBoxLayout(self)
        heading = QHBoxLayout()
        title = QLabel("Facilities, layouts & relocation")
        title.setStyleSheet("font-size: 22px; font-weight: 700")
        heading.addWidget(title)
        heading.addStretch()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        heading.addWidget(refresh)
        outer.addLayout(heading)

        intro = QLabel(
            "Current physical locations remain authoritative. Future floorplans and planned placements "
            "can be prepared without changing live inventory, then executed through an auditable relocation campaign."
        )
        intro.setWordWrap(True)
        outer.addWidget(intro)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self._build_floorplans_tab()
        self._build_layouts_tab()
        self._build_relocation_tab()
        self.refresh()

    @staticmethod
    def _table(headers: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    @staticmethod
    def _load(table: QTableWidget, rows: list[tuple[object, ...]]) -> None:
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                table.setItem(r, c, QTableWidgetItem("" if value is None else str(value)))
        table.resizeColumnsToContents()

    def _build_floorplans_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.floorplans = self._table(("Title", "Version", "Status", "Location", "SVG", "Source format", "Drawing id"))
        self.floorplans.setColumnHidden(6, True)
        layout.addWidget(self.floorplans, 1)
        row = QHBoxLayout()
        for text, handler in (
            ("Open interactive floorplan", self._open_floorplan),
            ("Open selected location", self._open_floorplan_location),
            ("Set operational SVG", self._set_svg),
            ("Set revision status", self._set_revision_status),
            ("Activate revision", self._activate_revision),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.tabs.addTab(page, "Floorplans")

    def _build_layouts_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        split = QSplitter(Qt.Orientation.Vertical)
        upper = QWidget()
        upper_layout = QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.addWidget(QLabel("Future layouts"))
        self.layouts = self._table(("Name", "Version", "Status", "Effective", "Location", "Floorplan", "Plan id"))
        self.layouts.setColumnHidden(6, True)
        self.layouts.itemSelectionChanged.connect(self._layout_selected)
        upper_layout.addWidget(self.layouts)
        row = QHBoxLayout()
        for text, handler in (
            ("New future layout", self._new_layout),
            ("Plan asset placement", self._plan_asset),
            ("Open target floorplan", self._open_plan_floorplan),
            ("Change status", self._change_layout_status),
            ("Create relocation campaign", self._create_campaign),
            ("Export picklist", self._export_layout_picklist),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            row.addWidget(button)
        row.addStretch()
        upper_layout.addLayout(row)
        split.addWidget(upper)

        lower = QWidget()
        lower_layout = QVBoxLayout(lower)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.addWidget(QLabel("Planned placements — live locations are unchanged until execution"))
        self.placements = self._table(("Resource", "Name", "Current location", "Target location", "Status", "Placement id"))
        self.placements.setColumnHidden(5, True)
        lower_layout.addWidget(self.placements)
        split.addWidget(lower)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 2)
        layout.addWidget(split, 1)
        self.tabs.addTab(page, "Future layouts")

    def _build_relocation_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Relocation campaigns"))
        self.campaigns = self._table(("Name", "Status", "Start", "End", "Campaign id"))
        self.campaigns.setColumnHidden(4, True)
        self.campaigns.itemSelectionChanged.connect(self._campaign_selected)
        left_layout.addWidget(self.campaigns)
        campaign_actions = QHBoxLayout()
        for text, handler in (
            ("Start / change status", self._change_campaign_status),
            ("Export move list", self._export_campaign),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            campaign_actions.addWidget(button)
        campaign_actions.addStretch()
        left_layout.addLayout(campaign_actions)
        split.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.progress = QLabel("Select a relocation campaign")
        self.progress.setWordWrap(True)
        right_layout.addWidget(self.progress)
        self.steps = self._table(("Resource", "Name", "From", "To", "State", "Step id"))
        self.steps.setColumnHidden(5, True)
        right_layout.addWidget(self.steps, 1)
        states = QHBoxLayout()
        for state in ("removed", "in_transit", "staging", "stored", "placed", "displayed", "exception"):
            button = QPushButton(state.replace("_", " ").title())
            button.clicked.connect(lambda _checked=False, value=state: self._record_step(value))
            states.addWidget(button)
        right_layout.addLayout(states)
        split.addWidget(right)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        layout.addWidget(split, 1)
        self.tabs.addTab(page, "Relocation")

    def refresh(self) -> None:
        actor = self.actor()
        drawings = list(self.service.drawings(actor))
        self._load(
            self.floorplans,
            [
                (
                    row.get("title"),
                    row.get("version"),
                    row.get("status"),
                    self.service.location_path(row.get("location_id"), actor),
                    row.get("operational_svg_path") or "—",
                    row.get("source_format"),
                    row.get("id"),
                )
                for row in drawings
            ],
        )
        self._plans = list(self.service.layout_plans(actor))
        self._load(
            self.layouts,
            [
                (
                    row.get("name"),
                    row.get("version"),
                    row.get("status"),
                    row.get("effective_at"),
                    self.service.location_path(row.get("location_id"), actor),
                    row.get("drawing_title") or "—",
                    row.get("id"),
                )
                for row in self._plans
            ],
        )
        self._campaigns = list(self.service.relocation_campaigns(actor))
        self._load(
            self.campaigns,
            [
                (row.get("name"), row.get("status"), row.get("scheduled_start"), row.get("scheduled_end"), row.get("id"))
                for row in self._campaigns
            ],
        )
        self._layout_selected()
        self._campaign_selected()

    def _selected_hidden_id(self, table: QTableWidget, column: int) -> str:
        rows = table.selectionModel().selectedRows() if table.selectionModel() else []
        if not rows:
            return ""
        item = table.item(rows[0].row(), column)
        return item.text() if item else ""

    def _open_floorplan(self) -> None:
        drawing_id = self._selected_hidden_id(self.floorplans, 6)
        if not drawing_id:
            QMessageBox.information(self, "Floorplan", "Select a drawing first.")
            return
        FacilityFloorplanDialog(self.service, actor=self.actor(), drawing_id=drawing_id, editable=True, parent=self).exec()
        self.refresh()

    def _open_floorplan_location(self) -> None:
        drawing_id = self._selected_hidden_id(self.floorplans, 6)
        if not drawing_id:
            QMessageBox.information(self, "Floorplan", "Select a drawing first.")
            return
        locations = list(self.service.locations_on_drawing(drawing_id, self.actor()))
        if not locations:
            QMessageBox.information(self, "Floorplan", "No locations are mapped on this drawing yet.")
            return
        labels = [self.service.location_path(row["id"], self.actor()) for row in locations]
        choice, ok = QInputDialog.getItem(self, "Show location", "Location", labels, 0, False)
        if not ok:
            return
        location_id = str(locations[labels.index(choice)]["id"])
        FacilityFloorplanDialog(
            self.service,
            actor=self.actor(),
            drawing_id=drawing_id,
            location_id=location_id,
            editable=True,
            parent=self,
        ).exec()

    def _set_svg(self) -> None:
        drawing_id = self._selected_hidden_id(self.floorplans, 6)
        if not drawing_id:
            QMessageBox.information(self, "Operational SVG", "Select a drawing first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Operational floorplan SVG", "", "SVG files (*.svg)")
        if not path:
            return
        try:
            self.service.set_operational_svg(drawing_id, actor=self.actor(), svg_path=path)
        except Exception as exc:
            QMessageBox.warning(self, "Operational SVG", str(exc))
            return
        self.refresh()

    def _set_revision_status(self) -> None:
        drawing_id = self._selected_hidden_id(self.floorplans, 6)
        if not drawing_id:
            QMessageBox.information(self, "Floorplan revision", "Select a drawing first.")
            return
        states = ("draft", "planned", "approved", "scheduled", "current", "superseded", "archived")
        status, ok = QInputDialog.getItem(self, "Floorplan revision", "Status", states, 0, False)
        if not ok:
            return
        try:
            self.service.update_drawing_revision(drawing_id, actor=self.actor(), status=status)
        except Exception as exc:
            QMessageBox.warning(self, "Floorplan revision", str(exc))
            return
        self.refresh()

    def _activate_revision(self) -> None:
        drawing_id = self._selected_hidden_id(self.floorplans, 6)
        if not drawing_id:
            QMessageBox.information(self, "Activate floorplan", "Select a drawing first.")
            return
        effective, ok = QInputDialog.getText(
            self,
            "Activate floorplan",
            "Effective date/time",
            text=datetime.now().isoformat(timespec="seconds"),
        )
        if not ok:
            return
        if QMessageBox.question(
            self,
            "Activate floorplan",
            "Make this revision current and supersede the previous current revision for the same location?",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.activate_drawing_revision(drawing_id, actor=self.actor(), effective_at=effective)
        except Exception as exc:
            QMessageBox.warning(self, "Activate floorplan", str(exc))
            return
        self.refresh()

    def _new_layout(self) -> None:
        name, ok = QInputDialog.getText(self, "Future layout", "Plan name")
        if not ok or not name.strip():
            return
        drawings = list(self.service.drawings(self.actor()))
        labels = ["No drawing"] + [f"{d['title']} · {d.get('version') or 'unversioned'} · {d.get('status')}" for d in drawings]
        selected, ok = QInputDialog.getItem(self, "Future layout", "Target floorplan", labels, 0, False)
        if not ok:
            return
        drawing = None if selected == "No drawing" else drawings[labels.index(selected) - 1]
        version, ok = QInputDialog.getText(self, "Future layout", "Plan version")
        if not ok:
            return
        effective, ok = QInputDialog.getText(self, "Future layout", "Planned effective date/time")
        if not ok:
            return
        try:
            self.service.create_layout_plan(
                name,
                actor=self.actor(),
                location_id=drawing.get("location_id") if drawing else None,
                drawing_id=drawing.get("id") if drawing else None,
                version=version,
                status="draft",
                effective_at=effective,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Future layout", str(exc))
            return
        self.refresh()

    def _selected_plan(self) -> dict | None:
        plan_id = self._selected_hidden_id(self.layouts, 6)
        return next((row for row in self._plans if str(row.get("id")) == plan_id), None)

    def _layout_selected(self) -> None:
        plan = self._selected_plan()
        self._placements = list(self.service.planned_placements(plan["id"], self.actor())) if plan else []
        self._load(
            self.placements,
            [
                (
                    row.get("asset_code") or row.get("resource_id"),
                    row.get("asset_name") or row.get("resource_type"),
                    self.service.location_path(row.get("current_location_id"), self.actor()),
                    self.service.location_path(row.get("target_location_id"), self.actor()),
                    row.get("status"),
                    row.get("id"),
                )
                for row in self._placements
            ],
        )

    def _plan_asset(self) -> None:
        plan = self._selected_plan()
        if not plan:
            QMessageBox.information(self, "Planned placement", "Select a future layout first.")
            return
        assets = list(self.service.assets(self.actor()))
        if not assets:
            QMessageBox.information(self, "Planned placement", "No accessible Operations assets exist.")
            return
        asset_labels = [f"{row['asset_code']} — {row['name']}" for row in assets]
        asset_choice, ok = QInputDialog.getItem(self, "Planned placement", "Resource", asset_labels, 0, False)
        if not ok:
            return
        locations = list(self.service.locations(self.actor()))
        location_labels = [self.service.location_path(row["id"], self.actor()) for row in locations]
        target, ok = QInputDialog.getItem(self, "Planned placement", "Target location", location_labels, 0, False)
        if not ok:
            return
        asset = assets[asset_labels.index(asset_choice)]
        location = locations[location_labels.index(target)]
        try:
            self.service.plan_asset_placement(plan["id"], asset["id"], location["id"], actor=self.actor())
        except Exception as exc:
            QMessageBox.warning(self, "Planned placement", str(exc))
            return
        self._layout_selected()

    def _open_plan_floorplan(self) -> None:
        plan = self._selected_plan()
        if not plan or not plan.get("drawing_id"):
            QMessageBox.information(self, "Future layout", "The selected plan has no target floorplan.")
            return
        FacilityFloorplanDialog(
            self.service,
            actor=self.actor(),
            drawing_id=str(plan["drawing_id"]),
            editable=True,
            parent=self,
        ).exec()

    def _change_layout_status(self) -> None:
        plan = self._selected_plan()
        if not plan:
            QMessageBox.information(self, "Future layout", "Select a plan first.")
            return
        states = ("draft", "planned", "approved", "scheduled", "active", "completed", "cancelled", "archived")
        status, ok = QInputDialog.getItem(self, "Future layout", "Status", states, 0, False)
        if not ok:
            return
        try:
            self.service.set_layout_status(plan["id"], status, actor=self.actor())
        except Exception as exc:
            QMessageBox.warning(self, "Future layout", str(exc))
            return
        self.refresh()

    def _create_campaign(self) -> None:
        plan = self._selected_plan()
        if not plan:
            QMessageBox.information(self, "Relocation", "Select a future layout first.")
            return
        name, ok = QInputDialog.getText(self, "Relocation", "Campaign name", text=f"Move for {plan['name']}")
        if not ok or not name.strip():
            return
        try:
            campaign_id = self.service.create_relocation_campaign(name, actor=self.actor(), plan_id=plan["id"])
            self.service.set_relocation_status(campaign_id, "ready", actor=self.actor())
        except Exception as exc:
            QMessageBox.warning(self, "Relocation", str(exc))
            return
        self.refresh()
        self.tabs.setCurrentIndex(2)

    def _export_rows(self, rows: list[dict], default_name: str) -> None:
        if not rows:
            QMessageBox.information(self, "Export", "There is nothing to export.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", default_name, "CSV files (*.csv)")
        if not path:
            return
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        with Path(path).open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)

    def _export_layout_picklist(self) -> None:
        plan = self._selected_plan()
        if not plan:
            QMessageBox.information(self, "Picklist", "Select a future layout first.")
            return
        rows = list(self.service.placement_picklist(plan["id"], self.actor()))
        self._export_rows(rows, f"fieldora-layout-{plan['id'][:8]}-picklist.csv")

    def _selected_campaign(self) -> dict | None:
        campaign_id = self._selected_hidden_id(self.campaigns, 4)
        return next((row for row in self._campaigns if str(row.get("id")) == campaign_id), None)

    def _campaign_selected(self) -> None:
        campaign = self._selected_campaign()
        if not campaign:
            self._steps = []
            self._load(self.steps, [])
            self.progress.setText("Select a relocation campaign")
            return
        self._steps = list(self.service.relocation_picklist(campaign["id"], self.actor()))
        self._load(
            self.steps,
            [
                (
                    row.get("display_code"),
                    row.get("display_name"),
                    row.get("from_path"),
                    row.get("to_path"),
                    row.get("status"),
                    row.get("id"),
                )
                for row in self._steps
            ],
        )
        progress = self.service.relocation_progress(campaign["id"], self.actor())
        self.progress.setText(
            f"{campaign['name']} — {campaign['status']}\n"
            f"{progress['completed']} completed · {progress['outstanding']} outstanding · "
            f"{progress['exceptions']} exceptions · {progress['total']} total"
        )

    def _change_campaign_status(self) -> None:
        campaign = self._selected_campaign()
        if not campaign:
            QMessageBox.information(self, "Relocation", "Select a campaign first.")
            return
        states = ("draft", "ready", "in_progress", "paused", "completed", "cancelled", "archived")
        status, ok = QInputDialog.getItem(self, "Relocation", "Status", states, 0, False)
        if not ok:
            return
        try:
            self.service.set_relocation_status(campaign["id"], status, actor=self.actor())
        except Exception as exc:
            QMessageBox.warning(self, "Relocation", str(exc))
            return
        self.refresh()

    def _record_step(self, state: str) -> None:
        step_id = self._selected_hidden_id(self.steps, 5)
        if not step_id:
            QMessageBox.information(self, "Relocation", "Select a move step first.")
            return
        if state in _FINAL_STATES:
            answer = QMessageBox.question(
                self,
                "Confirm physical placement",
                "This state confirms the resource has reached its destination and may update its live location. Continue?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            self.service.record_relocation_step_state(
                step_id,
                state,
                actor=self.actor(),
                moved_at=datetime.now().isoformat(timespec="seconds"),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Relocation", str(exc))
            return
        self._campaign_selected()

    def _export_campaign(self) -> None:
        campaign = self._selected_campaign()
        if not campaign:
            QMessageBox.information(self, "Relocation", "Select a campaign first.")
            return
        rows = list(self.service.relocation_picklist(campaign["id"], self.actor()))
        self._export_rows(rows, f"fieldora-relocation-{campaign['id'][:8]}.csv")
