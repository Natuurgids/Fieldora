"""Ecological context settings workspace."""

from pathlib import Path

try:
    from PySide6.QtWidgets import (
        QDialog,
        QDialogButtonBox,
        QFileDialog,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:
    raise RuntimeError("PySide6 is required") from exc


class _ImportPreviewDialog(QDialog):
    def __init__(self, service, preview, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._preview = preview
        self.import_requested = False
        self.setWindowTitle("Ecological context import preview")
        self.resize(920, 560)
        summary = QLabel(
            f"Matched: {preview.matched_count}    Unmatched: {preview.unmatched_count}    Total: {len(preview.rows)}"
        )
        summary.setStyleSheet("font-size: 15px; font-weight: 600;")
        info = QLabel(
            "Exact and safely normalized matches can be imported. Unmatched rows are skipped. Review suggestions before continuing."
        )
        info.setWordWrap(True)
        table = QTableWidget(len(preview.rows), 4)
        table.setHorizontalHeaderLabels(
            ("CSV scientific name", "Installed accepted name", "Match", "Suggestion")
        )
        for i, row in enumerate(preview.rows):
            values = (
                row.scientific_name,
                row.matched_scientific_name or "",
                row.match_kind.replace("_", " ").title(),
                row.suggestion or "",
            )
            for j, value in enumerate(values):
                table.setItem(i, j, QTableWidgetItem(value))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        report = buttons.addButton("Save unmatched report…", QDialogButtonBox.ActionRole)
        report.setEnabled(preview.unmatched_count > 0)
        report.clicked.connect(self._report)
        install = buttons.addButton(
            f"Import {preview.matched_count} matched row(s)", QDialogButtonBox.AcceptRole
        )
        install.setEnabled(preview.matched_count > 0)
        install.clicked.connect(self._accept_import)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(summary)
        layout.addWidget(info)
        layout.addWidget(table)
        layout.addWidget(buttons)

    def _accept_import(self) -> None:
        self.import_requested = True
        self.accept()

    def _report(self) -> None:
        name, _ = QFileDialog.getSaveFileName(
            self,
            "Save unmatched-row report",
            "ecological-context-unmatched.csv",
            "CSV files (*.csv)",
        )
        if name:
            count = self._service.write_unmatched_report(self._preview, Path(name))
            QMessageBox.information(self, "Unmatched report", f"Saved {count} unmatched row(s).")


class EcologicalContextWorkspace(QWidget):
    def __init__(self, service, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._status = QLabel()
        self._status.setWordWrap(True)
        title = QLabel("Conservation & Seasonality")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        info = QLabel(
            "Import a local CSV containing conservation status, seasonal months, migration status, habitats, and source attribution. NatureAI previews taxonomy matches before writing anything and can normalize authorship suffixes and hybrid symbols."
        )
        info.setWordWrap(True)
        button = QPushButton("Preview and import ecological context CSV…")
        button.clicked.connect(self._import)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        row = QHBoxLayout()
        row.addWidget(button)
        row.addWidget(refresh)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(self._status)
        layout.addLayout(row)
        layout.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        self._status.setText(f"Installed ecological context records: {self._service.count()}")

    def _import(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, "Import ecological context CSV", "", "CSV files (*.csv)"
        )
        if not name:
            return
        try:
            preview = self._service.preview_csv(Path(name))
            dialog = _ImportPreviewDialog(self._service, preview, self)
            if dialog.exec() != QDialog.Accepted or not dialog.import_requested:
                return
            count = self._service.import_preview(preview)
            self.refresh()
            QMessageBox.information(
                self,
                "Ecological context",
                f"Imported {count} matching taxon record(s).\nSkipped {preview.unmatched_count} unmatched row(s).",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Ecological context", str(exc))
