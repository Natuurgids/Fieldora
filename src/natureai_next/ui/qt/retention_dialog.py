"""Qt dialog for deliberate canonical-enrichment slimming."""

from __future__ import annotations

from natureai_next.application.enrichment_retention_ui import (
    EnrichmentRetentionController,
    RetentionPreview,
)
from natureai_next.application.retention import RetentionProfileName

try:
    from PySide6.QtCore import Slot
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QLabel,
        QMessageBox,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


class EnrichmentRetentionDialog(QDialog):
    def __init__(
        self, controller: EnrichmentRetentionController, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._preview: RetentionPreview | None = None
        self.setWindowTitle("Slim Aperture enrichment")
        self._profile = QComboBox()
        for profile in RetentionProfileName:
            self._profile.addItem(profile.value.title(), profile)
        self._delete_accepted = QCheckBox("Delete accepted shapes not retained by this profile")
        self._delete_accepted.setToolTip("Destructive and disabled by default.")
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        buttons.rejected.connect(self.reject)
        self._profile.currentIndexChanged.connect(self._refresh)
        self._delete_accepted.toggled.connect(self._refresh)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Retention profile"))
        layout.addWidget(self._profile)
        layout.addWidget(self._delete_accepted)
        layout.addWidget(self._summary)
        layout.addWidget(buttons)
        self._refresh()

    @Slot()
    def _refresh(self) -> None:
        profile = self._profile.currentData()
        self._preview = self._controller.preview(
            profile, delete_unselected_accepted=self._delete_accepted.isChecked()
        )
        report = self._preview.report
        self._summary.setText(
            f"Records eligible for deletion: {report.records_deleted}\n"
            f"Accepted records eligible: {report.accepted_records_deleted}\n"
            f"Accepted records preserved: {report.accepted_records_preserved}\n"
            f"Payloads to slim: {report.payload_documents_slimmed}\n"
            f"Evidence documents to slim: {report.evidence_documents_slimmed}\n"
            f"Probability vectors: {report.probability_vectors_removed}\n"
            f"Diagnostics: {report.diagnostics_removed}\n"
            f"Temporary/cache references: {report.temporary_artifacts_removed + report.media_cache_references_removed}\n"
            f"OCR intermediates: {report.ocr_intermediates_removed}\n"
            f"Source packages/indexes: {report.source_package_references_removed}\n"
            f"Records with reduced reproducibility: {report.reproducibility_impacted_records}"
        )

    @Slot()
    def _apply(self) -> None:
        if self._preview is None:
            return
        if self._preview.destructive_accepted_delete:
            answer = QMessageBox.warning(
                self,
                "Delete accepted enrichment?",
                "This explicitly removes accepted structural knowledge. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        report = self._controller.apply(self._preview)
        QMessageBox.information(
            self, "Slimming complete", f"Removed {report.records_deleted} record(s)."
        )
        self.accept()
