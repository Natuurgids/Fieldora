"""Build 28 Storage Manager workspace."""
from __future__ import annotations

from pathlib import Path

from natureai_next.application.storage import AssetStorageService
from natureai_next.ui.qt.activity import activity_center

try:
    from PySide6.QtCore import Qt, Slot
    from PySide6.QtWidgets import (
        QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget,
        QTableWidgetItem, QVBoxLayout, QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


class StorageManagerWorkspace(QWidget):
    """Verify, relink and consolidate original storage without decoding media."""

    def __init__(self, database_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = AssetStorageService(database_path)
        self._activity_center = activity_center()
        self._seen_completed_verifications: set[str] = set()
        self._activity_center.changed.connect(self._activity_changed)
        title = QLabel("Storage Manager")
        title.setObjectName("libraryTitle")
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._table = QTableWidget(0, 10)
        self._table.setHorizontalHeaderLabels(
            ["Asset", "Storage", "Role", "Device", "Device ID", "Status", "Size", "Relative path", "Current mount", "Resolved location"]
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self._table.horizontalHeader().setStretchLastSection(True)

        refresh = QPushButton("Refresh")
        verify = QPushButton("Verify selected")
        verify_all = QPushButton("Verify all")
        relink = QPushButton("Relink source…")
        create_master = QPushButton("Create Managed Copy")
        remove_master = QPushButton("Remove Selected Copies")
        remove_folder = QPushButton("Remove by Folder…")
        remove_drive = QPushButton("Remove by Drive…")
        refresh.clicked.connect(self.refresh)
        verify.clicked.connect(lambda: self._verify(False))
        verify_all.clicked.connect(lambda: self._verify(True))
        relink.clicked.connect(self._relink)
        create_master.clicked.connect(self._create_master)
        remove_master.clicked.connect(self._remove_master)
        remove_folder.clicked.connect(self._remove_folder)
        remove_drive.clicked.connect(self._remove_drive)
        buttons = QHBoxLayout()
        for button in (refresh, verify, verify_all, relink, create_master, remove_master, remove_folder, remove_drive):
            buttons.addWidget(button)
        buttons.addStretch(1)

        note = QLabel(
            "Linked originals remain outside Aperture. Removing an Aperture original is allowed only "
            "when a source reference exists. Verification can detect missing or externally changed files."
        )
        note.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self._summary)
        layout.addLayout(buttons)
        layout.addWidget(self._table, 1)
        layout.addWidget(note)

    @Slot()
    def refresh(self) -> None:
        try:
            stats = self._service.statistics()
            self._summary.setText(
                f"{stats.assets} assets — {stats.managed_assets} managed, "
                f"{stats.referenced_assets} linked, {stats.hybrid_assets} hybrid — "
                f"{stats.unavailable_locations} unavailable — {self._format_bytes(stats.managed_bytes)} managed originals"
            )
            rows = self._service.list_locations()
            self._table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                values = (
                    row["asset_public_id"], ("linked" if row["policy"] == "referenced" else (row["policy"] or "unknown")), row["role"],
                    row["volume_label"] or row["provider_name"], row["device_identity"] or "Aperture Library",
                    row["health"], self._format_bytes(row["file_size"] or 0), row["relative_path"] or "—",
                    row["last_mount_path"] or "—", row["normalized_path"],
                )
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                    item.setData(Qt.ItemDataRole.UserRole + 1, int(row["asset_id"]))
                    item.setData(Qt.ItemDataRole.UserRole + 2, str(row["role"]))
                    self._table.setItem(index, column, item)
        except Exception as exc:
            self._summary.setText(f"Storage Manager unavailable: {exc}")

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh()

    def _selected(self) -> list[tuple[int, int, str]]:
        values = []
        for index in sorted({item.row() for item in self._table.selectedItems()}):
            item = self._table.item(index, 0)
            values.append((int(item.data(Qt.ItemDataRole.UserRole)),
                           int(item.data(Qt.ItemDataRole.UserRole + 1)),
                           str(item.data(Qt.ItemDataRole.UserRole + 2))))
        return values

    def _verify(self, all_locations: bool) -> None:
        ids = None if all_locations else [location for location, _asset, _role in self._selected()]
        if ids == []:
            QMessageBox.information(self, "Storage Manager", "Select one or more storage locations.")
            return
        count = self._service.statistics().assets if all_locations else len(ids)

        def operation(progress, cancelled) -> str:
            results = self._service.verify(
                ids, progress=progress, cancelled=cancelled, commit_batch_size=50
            )
            changed = sum(result.health != "available" for result in results)
            return (
                f"Verified {len(results):,} storage location(s); "
                f"{changed:,} require attention."
            )

        record = self._activity_center.start(
            "Verify all storage" if all_locations else "Verify selected storage",
            f"{count:,} asset(s)",
            operation,
            kind="storage.verify",
            payload={"all_locations": all_locations, "location_ids": ids or []},
        )
        self._summary.setText(
            f"Storage verification queued in Activity Center ({record.detail}). "
            "The Storage Manager remains available while verification runs."
        )

    @Slot()
    def _activity_changed(self) -> None:
        for record in self._activity_center.records:
            if record.kind != "storage.verify" or record.state not in {"completed", "failed", "cancelled"}:
                continue
            if record.activity_id in self._seen_completed_verifications:
                continue
            self._seen_completed_verifications.add(record.activity_id)
            self.refresh()
            break

    def _relink(self) -> None:
        selected = self._selected()
        if len(selected) != 1 or selected[0][2] != "source":
            QMessageBox.information(self, "Relink", "Select exactly one source location.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Locate original")
        if not path:
            return
        try:
            self._service.relink(selected[0][0], Path(path))
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Relink", str(exc))

    def _create_master(self) -> None:
        assets = {asset for _location, asset, _role in self._selected()}
        if len(assets) != 1:
            QMessageBox.information(self, "Create Managed Copy", "Select a location for exactly one asset.")
            return
        try:
            destination = self._service.create_aperture_master(next(iter(assets)))
            QMessageBox.information(self, "Create Managed Copy", f"Verified Aperture original created at:\n{destination}")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Create Managed Copy", str(exc))

    def _remove_master(self) -> None:
        assets = {asset for _location, asset, _role in self._selected()}
        if not assets:
            QMessageBox.information(self, "Remove Managed Copies", "Select one or more rows. All selected rows for the same observation count once.")
            return
        self._remove_assets(sorted(assets), "selected observations")

    def _remove_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose storage folder")
        if folder:
            self._remove_assets(self._service.assets_in_storage_scope(Path(folder)), f"folder {folder}")

    def _remove_drive(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder on the storage drive")
        if not folder:
            return
        path = Path(folder).resolve(strict=False)
        anchor = Path(path.anchor) if path.anchor else path
        self._remove_assets(self._service.assets_in_storage_scope(anchor), f"drive {anchor}")

    def _remove_assets(self, asset_ids: list[int], scope_label: str) -> None:
        if not asset_ids:
            QMessageBox.information(self, "Remove Managed Copies", f"No observations were found in {scope_label}.")
            return
        try:
            preview = self._service.managed_removal_preview(asset_ids)
            if preview.managed_copies == 0:
                QMessageBox.information(self, "Remove Managed Copies", "No managed copies were found in this scope.")
                return
            message = (
                f"Scope: {scope_label}\n\n"
                f"Managed copies found: {preview.managed_copies}\n"
                f"Safe to remove: {len(preview.removable_asset_ids)}\n"
                f"Blocked (no available linked source): {len(preview.blocked_asset_ids)}\n"
                f"Estimated space reclaimed: {self._format_bytes(preview.reclaimable_bytes)}\n\n"
                "Remove all safe managed copies? Observations and source references will be retained."
            )
            if QMessageBox.question(self, "Remove Managed Copies", message) != QMessageBox.StandardButton.Yes:
                return
            completed = self._service.remove_aperture_masters(preview.removable_asset_ids)
            QMessageBox.information(
                self, "Remove Managed Copies",
                f"Removed {len(completed.removable_asset_ids)} managed copy/copies. "
                f"{len(preview.blocked_asset_ids)} observation(s) were left unchanged.",
            )
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Remove Managed Copies", f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _format_bytes(value: int) -> str:
        amount = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if amount < 1024 or unit == "TB":
                return f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{value} B"
