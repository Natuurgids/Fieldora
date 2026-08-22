"""Dedicated Marine Science and Maritime Operations desktop workspaces."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from natureai_next.ui.qt.date_time_input import DateTimeTextField
from natureai_next.application.marine_maritime import (
    MARINE_RECORD_TYPES,
    MARITIME_RECORD_TYPES,
    MarineMaritimeService,
)

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


LABELS = {
    "sampling_station": "Sampling Stations",
    "survey": "Surveys",
    "sample": "Samples",
    "measurement": "Measurements",
    "species_observation": "Species Observations",
    "edna_sample": "eDNA Samples",
    "habitat": "Marine Habitats",
    "acoustic_sonar": "Acoustic & Sonar",
    "vessel": "Vessels",
    "voyage": "Voyages",
    "port": "Ports",
    "route": "Routes",
    "crew": "Crew",
    "equipment": "Equipment",
    "dive": "Dives",
    "submarine_log": "Submarine Logs",
    "operation_log": "Operation Logs",
}


class MarineMaritimeWorkspace(QWidget):
    """Record-oriented UI with distinct screens for each scientific/operational type."""

    def __init__(
        self,
        database_path: Path,
        *,
        domain: str,
        selected_asset_ids: Callable[[], tuple[str, ...]] = tuple,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._domain = domain
        self._service = MarineMaritimeService(database_path)
        self._selected_asset_ids = selected_asset_ids
        self._tables: dict[str, QTableWidget] = {}
        title = (
            "Marine & Freshwater Science"
            if domain == "marine"
            else "Maritime Operations"
        )
        description = (
            "Manage sampling stations, surveys, samples, environmental measurements, "
            "species and eDNA evidence, habitats, acoustics and sonar."
            if domain == "marine"
            else "Coordinate vessels, voyages, ports, routes, crew, equipment, dives and "
            "submarine or field-operation logs without mixing operational records with "
            "observations."
        )
        heading = QLabel(f"<h2>{title}</h2>")
        intro = QLabel(description)
        intro.setWordWrap(True)
        nautical = QLabel(
            "<b>Offline nautical maps:</b> Install and enable prepared OpenSeaMap "
            "MBTiles overlays under Platform → Offline Maps. Nautical overlays are "
            "reference material and are not certified navigational charts."
        )
        nautical.setWordWrap(True)
        self._tabs = QTabWidget(self)
        record_types = MARINE_RECORD_TYPES if domain == "marine" else MARITIME_RECORD_TYPES
        for record_type in record_types:
            self._tabs.addTab(self._page(record_type), LABELS[record_type])
        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(intro)
        layout.addWidget(nautical)
        layout.addWidget(self._tabs, 1)
        self.refresh()

    def _page(self, record_type: str) -> QWidget:
        page = QWidget()
        headers = [
            "Name", "Status", "Owner", "Start", "End", "Location",
            "Depth (m)",
        ]
        if record_type == "dive":
            headers.append("Buddy / dive partner")
        headers.append("Attachments")
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tables[record_type] = table
        add = QPushButton(f"New {LABELS[record_type].rstrip('s')}")
        add.clicked.connect(lambda checked=False, kind=record_type: self._create(kind))
        attach = QPushButton("Attach selected library media")
        attach.clicked.connect(lambda checked=False, kind=record_type: self._attach(kind))
        remove = QPushButton("Delete")
        remove.clicked.connect(lambda checked=False, kind=record_type: self._delete(kind))
        export = QPushButton("Export domain JSON")
        export.clicked.connect(self._export)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        buttons = QHBoxLayout()
        for button in (add, attach, remove, export, refresh):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addLayout(buttons)
        layout.addWidget(table, 1)
        return page

    def _create(self, record_type: str) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(f"New {LABELS[record_type]}")
        name = QLineEdit()
        status = QComboBox()
        status.addItems(("planned", "active", "blocked", "completed", "cancelled"))
        owner = QLineEdit()
        start = DateTimeTextField()
        end = DateTimeTextField()
        latitude = QLineEdit()
        longitude = QLineEdit()
        depth = QLineEdit()
        depth.setPlaceholderText("Metres below surface")
        buddy = QLineEdit()
        notes = QTextEdit()
        form = QFormLayout()
        form.addRow("Name*", name)
        form.addRow("Status", status)
        form.addRow("Owner / lead", owner)
        form.addRow("Start", start)
        form.addRow("End", end)
        form.addRow("Latitude", latitude)
        form.addRow("Longitude", longitude)
        form.addRow("Depth (m)", depth)
        if record_type == "dive":
            form.addRow("Buddy / dive partner", buddy)
        form.addRow("Notes", notes)
        save = QPushButton("Create")
        cancel = QPushButton("Cancel")
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(save)
        buttons.addWidget(cancel)
        layout = QVBoxLayout(dialog)
        layout.addLayout(form)
        layout.addLayout(buttons)
        cancel.clicked.connect(dialog.close)

        def persist() -> None:
            try:
                lat = float(latitude.text()) if latitude.text().strip() else None
                lon = float(longitude.text()) if longitude.text().strip() else None
                depth_m = float(depth.text()) if depth.text().strip() else None
                self._service.create(
                    domain=self._domain,
                    record_type=record_type,
                    name=name.text(),
                    status=status.currentText(),
                    owner=owner.text(),
                    start_at=start.text(),
                    end_at=end.text(),
                    latitude=lat,
                    longitude=lon,
                    depth_m=depth_m,
                    buddy=buddy.text(),
                    notes=notes.toPlainText(),
                )
            except ValueError as exc:
                QMessageBox.warning(dialog, "Cannot create record", str(exc))
                return
            dialog.close()
            self.refresh()

        save.clicked.connect(persist)
        dialog.setMinimumWidth(520)
        dialog.show()
        self._record_dialog = dialog

    def _selected_record_id(self, record_type: str) -> str | None:
        table = self._tables[record_type]
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        return None if item is None else item.data(256)

    def _attach(self, record_type: str) -> None:
        record_id = self._selected_record_id(record_type)
        if record_id is None:
            QMessageBox.information(self, "Attach media", "Select a record first.")
            return
        assets = self._selected_asset_ids()
        if not assets:
            QMessageBox.information(
                self, "Attach media", "Select photos, sounds, videos or documents first."
            )
            return
        added = self._service.attach_assets(str(record_id), assets)
        QMessageBox.information(self, "Attach media", f"{added} media item(s) attached.")
        self.refresh()

    def _delete(self, record_type: str) -> None:
        record_id = self._selected_record_id(record_type)
        if record_id is None:
            return
        if QMessageBox.question(
            self, "Delete record", "Delete this record and its attachment links?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._service.delete(str(record_id))
        self.refresh()

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export records",
            f"fieldora-{self._domain}-records.json",
            "JSON (*.json)",
        )
        if not path:
            return
        Path(path).write_text(
            json.dumps(self._service.export_records(self._domain), indent=2),
            encoding="utf-8",
        )

    def refresh(self) -> None:
        for record_type, table in self._tables.items():
            records = self._service.list(self._domain, record_type)
            table.setRowCount(len(records))
            for row, record in enumerate(records):
                location = ""
                if record.latitude is not None and record.longitude is not None:
                    location = f"{record.latitude:.6f}, {record.longitude:.6f}"
                values = [
                    record.name,
                    record.status,
                    record.owner,
                    record.start_at,
                    record.end_at,
                    location,
                    "" if record.depth_m is None else f"{record.depth_m:g}",
                ]
                if record_type == "dive":
                    values.append(record.buddy)
                values.append(str(len(self._service.attachment_ids(record.record_id))))
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 0:
                        item.setData(256, record.record_id)
                    table.setItem(row, column, item)
            table.resizeColumnsToContents()
