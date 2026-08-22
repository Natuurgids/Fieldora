"""Aperture Health Center workspace."""

from __future__ import annotations

import html
import importlib.metadata
import platform

from natureai_next.application.health import HealthReport, HealthSeverity, LibraryHealthService

try:
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required") from exc


class HealthCheckWidget(QWidget):
    backup_requested = Signal()
    restore_requested = Signal()
    updates_requested = Signal()

    def __init__(self, service: LibraryHealthService | None = None, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._details = QTextBrowser()
        self._details.setOpenExternalLinks(False)

        refresh = QPushButton("Run Health Check")
        refresh.setAccessibleName("Run Aperture library health check")
        refresh.clicked.connect(self.refresh)
        full = QPushButton("Run Full Database Check")
        full.setAccessibleName("Run full SQLite database integrity check")
        full.clicked.connect(self.run_full_check)
        repair = QPushButton("Repair Safe Items")
        repair.setAccessibleName("Repair missing folders and stale temporary files")
        repair.clicked.connect(self.repair_safe_items)
        backup = QPushButton("Back Up Library…")
        backup.setAccessibleName("Back up the current Aperture library")
        backup.clicked.connect(self.backup_requested)
        restore = QPushButton("Restore Library…")
        restore.setAccessibleName("Restore an Aperture library backup")
        restore.clicked.connect(self.restore_requested)
        updates = QPushButton("Check for Updates…")
        updates.setAccessibleName("Check the configured location for Aperture updates")
        updates.clicked.connect(self.updates_requested)

        primary = QHBoxLayout()
        for button in (refresh, full, repair):
            primary.addWidget(button)
        primary.addStretch(1)
        actions = QHBoxLayout()
        for button in (backup, restore, updates):
            actions.addWidget(button)
        actions.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Aperture Health Center</h2>"))
        layout.addWidget(
            QLabel(
                "Verify the current library, storage, backups, update source, and rebuildable data. "
                "Repairs are deliberately limited to safe operations that do not alter originals or confirmed metadata."
            )
        )
        layout.addLayout(primary)
        layout.addLayout(actions)
        layout.addWidget(self._summary)
        layout.addWidget(self._details, 1)
        self.refresh()

    def refresh(self) -> None:
        if self._service is None:
            self._show_environment_only()
            return
        self._render(self._service.assess())

    def run_full_check(self) -> None:
        if self._service is None:
            self._show_environment_only()
            return
        self._render(self._service.assess(full_database_check=True))

    def repair_safe_items(self) -> None:
        if self._service is None:
            QMessageBox.information(
                self, "Health Center", "No open library is available for repair."
            )
            return
        result = self._service.repair_safe_items()
        message = "\n".join(result.repaired or result.skipped)
        QMessageBox.information(self, "Safe repair completed", message)
        self.refresh()

    def _render(self, report: HealthReport) -> None:
        if report.error_count:
            status = (
                f"Action required: {report.error_count} error(s), {report.warning_count} warning(s)"
            )
        elif report.warning_count:
            status = f"Usable with attention: {report.warning_count} warning(s)"
        else:
            status = "Healthy: all checks passed"
        self._summary.setText(
            f"<b>{html.escape(status)}</b><br>Checked {html.escape(report.generated_at_utc)}"
        )
        icon = {HealthSeverity.OK: "✓", HealthSeverity.WARNING: "⚠", HealthSeverity.ERROR: "✕"}
        blocks = []
        for check in report.checks:
            repair = " <i>(safe repair available)</i>" if check.repairable else ""
            detail = f"<br><small>{html.escape(check.detail)}</small>" if check.detail else ""
            blocks.append(
                f"<p><b>{icon[check.severity]} {html.escape(check.title)}</b><br>"
                f"{html.escape(check.summary)}{repair}{detail}</p>"
            )
        self._details.setHtml("".join(blocks))

    def _show_environment_only(self) -> None:
        rows = []
        for label, package in (
            ("NatureAI_Next", "natureai-next"),
            ("PySide6", "PySide6"),
            ("PyTorch", "torch"),
            ("OpenCLIP", "open-clip-torch"),
        ):
            try:
                rows.append(f"✓ {label}: {importlib.metadata.version(package)}")
            except importlib.metadata.PackageNotFoundError:
                rows.append(f"⚠ {label}: not installed")
        rows.append(f"✓ Operating system: {platform.platform()}")
        self._summary.setText("<b>Environment information</b>")
        self._details.setHtml("<p>" + "<br>".join(html.escape(row) for row in rows) + "</p>")


class HealthCheckDialog(QDialog):
    def __init__(self, service: LibraryHealthService | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aperture Health Center")
        self.resize(760, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(HealthCheckWidget(service, self))
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
