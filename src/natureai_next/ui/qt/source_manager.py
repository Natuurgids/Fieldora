"""Managed enrichment source controls for the desktop shell."""

from __future__ import annotations

from natureai_next.application.source_lifecycle import (
    SourceRegistryService,
    SourceRemovalOptions,
    SourceState,
)
from natureai_next.application.source_lifecycle_ui import (
    present_source_state,
    preview_source_removal,
)

try:
    from PySide6.QtCore import Qt, Signal, Slot
    from PySide6.QtWidgets import (
        QCheckBox,
        QFileDialog,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


class EnrichmentSourceManagerWorkspace(QWidget):
    sources_changed = Signal()

    def __init__(
        self,
        registry: SourceRegistryService,
        parent: QWidget | None = None,
        *,
        bundle_installer=None,
        retention_controller=None,
        source_workspace=None,
    ) -> None:
        super().__init__(parent)
        self._registry = registry
        self._bundle_installer = bundle_installer
        self._retention_controller = retention_controller
        self._source_workspace = source_workspace
        title = QLabel("<h2>Enrichment Sources</h2>")
        intro = QLabel(
            "Manage installed capabilities and reference sources. Removing source files preserves accepted Aperture enrichment by default."
        )
        intro.setWordWrap(True)
        self._table = QTableWidget(0, 10)
        self._table.setHorizontalHeaderLabels(
            (
                "Name",
                "Kind",
                "Version",
                "State",
                "Pending",
                "Rejected",
                "Accepted",
                "Licence",
                "Attribution",
                "Checksum",
            )
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._selection_details)
        self._remove_pending = QCheckBox("Delete pending candidates")
        self._remove_rejected = QCheckBox("Delete rejected candidates")
        self._remove_rejected.setChecked(True)
        self._remove_accepted = QCheckBox("Delete accepted structural enrichment")
        self._remove_accepted.setToolTip(
            "Destructive: accepted evidence will no longer be readable."
        )
        install = QPushButton("Install offline bundle…")
        import_source = QPushButton("Import source data…")
        slim = QPushButton("Slim enrichment…")
        refresh = QPushButton("Refresh")
        activate = QPushButton("Activate")
        deactivate = QPushButton("Deactivate")
        verify = QPushButton("Verify files")
        relink = QPushButton("Relink runtime…")
        remove = QPushButton("Remove source files…")
        install.clicked.connect(self._install_bundle)
        import_source.clicked.connect(self._import_source)
        slim.clicked.connect(self._slim)
        install.setEnabled(self._bundle_installer is not None)
        import_source.setEnabled(self._source_workspace is not None)
        slim.setEnabled(self._retention_controller is not None)
        refresh.clicked.connect(self.refresh)
        activate.clicked.connect(self._activate)
        deactivate.clicked.connect(self._deactivate)
        verify.clicked.connect(self._verify)
        relink.clicked.connect(self._relink)
        remove.clicked.connect(self._remove)
        actions = QHBoxLayout()
        actions.addWidget(install)
        actions.addWidget(import_source)
        actions.addWidget(slim)
        actions.addWidget(refresh)
        actions.addWidget(activate)
        actions.addWidget(deactivate)
        actions.addWidget(verify)
        actions.addWidget(relink)
        actions.addWidget(remove)
        actions.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(self._table, 1)
        self._details = QLabel("Select a source to inspect its lifecycle state and provenance.")
        self._details.setWordWrap(True)
        layout.addWidget(self._details)
        layout.addWidget(self._remove_pending)
        layout.addWidget(self._remove_rejected)
        layout.addWidget(self._remove_accepted)
        layout.addLayout(actions)
        self.refresh()

    @Slot()
    def _install_bundle(self) -> None:
        if self._bundle_installer is None:
            return
        from natureai_next.ui.qt.bundle_dialog import OfflineBundleInstallAction

        if OfflineBundleInstallAction(self._bundle_installer, self).run():
            self.refresh()

    @Slot()
    def _import_source(self) -> None:
        if self._source_workspace is None:
            return
        descriptors = tuple(self._source_workspace.discover_sources())
        if not descriptors:
            QMessageBox.information(
                self, "Import source data", "No local source importers are available."
            )
            return
        labels = [f"{item.display_name} ({item.source_id})" for item in descriptors]
        selected, accepted = QInputDialog.getItem(
            self, "Import source data", "Importer", labels, 0, False
        )
        if not accepted:
            return
        descriptor = descriptors[labels.index(selected)]
        suffixes = sorted(descriptor.supported_suffixes)
        patterns = " ".join(f"*{suffix}" for suffix in suffixes) or "*"
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Select source package",
            "",
            f"{descriptor.display_name} ({patterns});;All files (*)",
        )
        if not path:
            return
        subject_type, accepted = QInputDialog.getItem(
            self,
            "Import source data",
            "Target subject type",
            ["observation", "photo", "sound", "video", "document"],
            0,
            False,
        )
        if not accepted:
            return
        subject_id, accepted = QInputDialog.getText(
            self, "Import source data", "Target subject public ID"
        )
        if not accepted or not subject_id.strip():
            return
        parameters = {}
        if descriptor.source_id == "org.aperture.geojson-reference":
            shape, accepted = QInputDialog.getItem(
                self,
                "GeoJSON output",
                "Canonical output",
                ["relationship", "bounding_box"],
                0,
                False,
            )
            if not accepted:
                return
            parameters["shape"] = shape
        try:
            from pathlib import Path

            from natureai_next.domain.enrichment import SubjectRef, SubjectType

            outcome = self._source_workspace.import_file(
                SubjectRef(SubjectType(subject_type), subject_id.strip()),
                source_id=descriptor.source_id,
                input_path=Path(path),
                parameters=parameters,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Source import failed", str(exc))
            return
        QMessageBox.information(
            self,
            "Source import complete",
            f"Created {len(outcome.created_enrichment_ids)} pending canonical enrichment record(s).",
        )
        self.refresh()

    @Slot()
    def _slim(self) -> None:
        if self._retention_controller is None:
            return
        from natureai_next.ui.qt.retention_dialog import EnrichmentRetentionDialog

        dialog = EnrichmentRetentionDialog(self._retention_controller, self)
        if dialog.exec():
            self.refresh()

    @Slot()
    def refresh(self) -> None:
        records = self._registry.list()
        self._table.setRowCount(len(records))
        for row_index, record in enumerate(records):
            counts = self._registry.enrichment_counts(record.source_id)
            state = present_source_state(record)
            values = (
                record.display_name,
                record.kind,
                record.version,
                state.label,
                str(counts.get("pending_review", 0) + counts.get("generated", 0)),
                str(counts.get("rejected", 0)),
                str(counts.get("accepted", 0)),
                record.licence or "—",
                record.attribution or "—",
                record.checksum or "—",
            )
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, record.source_id)
                self._table.setItem(row_index, column, cell)
        self._table.resizeColumnsToContents()
        self._selection_details()

    def _selected_source_id(self) -> str | None:
        row = self._table.currentRow()
        item = None if row < 0 else self._table.item(row, 0)
        return None if item is None else str(item.data(Qt.ItemDataRole.UserRole))

    @Slot()
    def _selection_details(self) -> None:
        source_id = self._selected_source_id()
        if source_id is None:
            self._details.setText("Select a source to inspect its lifecycle state and provenance.")
            return
        record = self._registry.get(source_id)
        state = present_source_state(record)
        parts = [f"{state.label}: {state.explanation}"]
        if record.licence:
            parts.append(f"Licence: {record.licence}")
        if record.attribution:
            parts.append(f"Attribution: {record.attribution}")
        if record.checksum:
            parts.append(f"Checksum: {record.checksum}")
        installation = self._registry.installation(source_id)
        if installation.runtime_path:
            parts.append(f"Runtime: {installation.runtime_path}")
        if installation.index_path:
            parts.append(f"Index/cache: {installation.index_path}")
        if installation.replacement_source_id:
            parts.append(f"Replacement: {installation.replacement_source_id}")
        if installation.last_error:
            parts.append(installation.last_error)
        self._details.setText("  •  ".join(parts))

    @Slot()
    def _activate(self) -> None:
        source_id = self._selected_source_id()
        if source_id is None:
            return
        record = self._registry.get(source_id)
        state = present_source_state(record)
        if not state.can_activate:
            QMessageBox.information(
                self,
                "Activate source",
                f"{record.display_name} cannot be activated from its current state: {state.label}.",
            )
            return
        self._registry.set_state(source_id, SourceState.INSTALLED)
        self.refresh()
        self.sources_changed.emit()

    @Slot()
    def _deactivate(self) -> None:
        source_id = self._selected_source_id()
        if source_id is None:
            return
        self._registry.set_state(source_id, SourceState.INACTIVE)
        self.refresh()
        self.sources_changed.emit()

    @Slot()
    def _verify(self) -> None:
        source_id = self._selected_source_id()
        if source_id is None:
            return
        state = self._registry.verify_installation(source_id)
        self.refresh()
        self.sources_changed.emit()
        record = self._registry.get(source_id)
        installation = self._registry.installation(source_id)
        if state is SourceState.MISSING:
            QMessageBox.warning(
                self,
                "Source files missing",
                installation.last_error or f"{record.display_name} files are missing.",
            )
        else:
            QMessageBox.information(
                self, "Source verified", f"{record.display_name} is {state.value}."
            )

    @Slot()
    def _relink(self) -> None:
        source_id = self._selected_source_id()
        if source_id is None:
            return
        path = QFileDialog.getExistingDirectory(self, "Select replacement runtime folder")
        if not path:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Select replacement runtime file", "", "All files (*)"
            )
            path = filename
        if not path:
            return
        try:
            self._registry.recover(source_id, runtime_path=__import__("pathlib").Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Source recovery failed", str(exc))
            return
        self.refresh()
        self.sources_changed.emit()
        QMessageBox.information(
            self, "Source recovered", "The source runtime was relinked and verified."
        )

    @Slot()
    def _remove(self) -> None:
        source_id = self._selected_source_id()
        if source_id is None:
            return
        destructive = self._remove_accepted.isChecked()
        options = SourceRemovalOptions(
            delete_pending_results=self._remove_pending.isChecked(),
            delete_rejected_results=self._remove_rejected.isChecked(),
            delete_accepted_enrichment=destructive,
        )
        preview = preview_source_removal(self._registry.enrichment_counts(source_id), options)
        answer = QMessageBox.question(
            self,
            "Remove enrichment source",
            "Remove the selected source runtime and managed files?\n\n" + preview.summary(),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._registry.remove(source_id, options)
        self.refresh()
        self.sources_changed.emit()
