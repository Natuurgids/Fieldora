"""Guided BioCLIP setup wizard with no hand-edited manifests."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from natureai_next.application.ai_setup import (
    BioCLIPQuickSetupService,
    BioCLIPSetupRequest,
    BioCLIPSetupResult,
)

try:
    from PySide6.QtCore import QObject, QThread, Signal, Slot
    from PySide6.QtWidgets import (
        QCheckBox,
        QDialog,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required") from exc


class _SetupWorker(QObject):
    progress = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service: BioCLIPQuickSetupService, request: BioCLIPSetupRequest) -> None:
        super().__init__()
        self._service = service
        self._request = request
        self._cancelled = threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.run(
                self._request,
                progress=lambda current, total, message: self.progress.emit(
                    current, total, message
                ),
                cancelled=self._cancelled.is_set,
            )
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    @Slot()
    def cancel(self) -> None:
        self._cancelled.set()


class BioCLIPSetupDialog(QDialog):
    """Downloads or imports BioCLIP, signs it locally, installs it, and optionally imports CSV taxonomy."""

    def __init__(self, service: BioCLIPQuickSetupService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._thread: QThread | None = None
        self._worker: _SetupWorker | None = None
        self.setWindowTitle("BioCLIP Quick Setup")
        self.setup_succeeded = False
        self.resize(820, 590)
        self.setMinimumSize(640, 480)

        intro = QLabel(
            "This wizard creates every NatureAI package and manifest automatically. "
            "Choose the complete supported BioCLIP model package (recommended), or select a checkpoint "
            "already stored on this computer. This installs the model required for AI Review; it is not "
            "the 92 TB occurrence corpus. An optional taxonomy CSV can contain columns "
            "scientific_name, common_name, rank, source_taxon_id, kingdom, major_group, "
            "language_tag, and region_code. The model checkpoint is separate from taxonomy data. "
            "For complete worldwide taxonomy, use Resources → Taxonomy Resources → "
            "Download complete GBIF Backbone Taxonomy; this is the taxonomy archive, not the multi-terabyte occurrence corpus."
        )
        intro.setWordWrap(True)

        default_root = (
            Path("D:/NatureAI-Models") if os.name == "nt" else Path.home() / "NatureAI-Models"
        )
        self._workspace = QLineEdit(str(default_root))
        self._model_folder = QLineEdit()
        self._checkpoint = QLineEdit()
        self._taxonomy = QLineEdit()
        self._download = QCheckBox(
            "Download complete supported BioCLIP model (recommended; not the 92 TB corpus)"
        )
        self._consent = QCheckBox(
            "I understand the checkpoint is obtained from Imageomics/Hugging Face under its upstream license."
        )
        self._download.toggled.connect(self._download_changed)

        form = QFormLayout()
        form.addRow(
            "Resource workspace", self._folder_row(self._workspace, "Select resource workspace")
        )
        form.addRow(
            "Complete BioCLIP folder",
            self._folder_row(self._model_folder, "Select complete BioCLIP model folder"),
        )
        form.addRow(
            "Checkpoint file (alternative)",
            self._file_row(self._checkpoint, "Model files (*.bin *.pt *.pth);;All files (*)"),
        )
        form.addRow("Taxonomy CSV (optional)", self._file_row(self._taxonomy, "CSV files (*.csv)"))

        self._start = QPushButton("Install complete BioCLIP model")
        self._cancel = QPushButton("Cancel download")
        self._cancel.setEnabled(False)
        self._close = QPushButton("Close")
        self._start.clicked.connect(self._begin)
        self._cancel.clicked.connect(self._cancel_download)
        self._close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addWidget(self._start)
        buttons.addWidget(self._cancel)
        buttons.addStretch(1)
        buttons.addWidget(self._close)

        self._progress = QProgressBar()
        self._progress.setRange(0, 7)
        self._progress.setValue(0)
        self._status = QLabel("Ready")
        self._status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self._download)
        layout.addWidget(self._consent)
        layout.addWidget(self._progress)
        layout.addWidget(self._status)
        layout.addLayout(buttons)
        self._download.setChecked(True)
        self._download_changed(True)

    def _folder_row(self, field: QLineEdit, title: str) -> QWidget:
        host = QWidget(self)
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Browse…")
        button.clicked.connect(lambda: self._pick_folder(field, title))
        layout.addWidget(field, 1)
        layout.addWidget(button)
        return host

    def _file_row(self, field: QLineEdit, pattern: str) -> QWidget:
        host = QWidget(self)
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Browse…")
        button.clicked.connect(lambda: self._pick_file(field, pattern))
        layout.addWidget(field, 1)
        layout.addWidget(button)
        return host

    def _pick_folder(self, field: QLineEdit, title: str) -> None:
        value = QFileDialog.getExistingDirectory(self, title, field.text())
        if value:
            field.setText(value)

    def _pick_file(self, field: QLineEdit, pattern: str) -> None:
        value, _ = QFileDialog.getOpenFileName(self, "Select local file", "", pattern)
        if value:
            field.setText(value)

    @Slot(bool)
    def _download_changed(self, enabled: bool) -> None:
        self._consent.setEnabled(enabled)
        self._model_folder.setEnabled(not enabled)
        self._checkpoint.setEnabled(not enabled)
        if not enabled:
            self._consent.setChecked(False)
        self._start.setText(
            "Download and install BioCLIP" if enabled else "Import and activate local BioCLIP"
        )

    @Slot()
    def _begin(self) -> None:
        if self._thread is not None:
            return
        if self._download.isChecked() and not self._consent.isChecked():
            QMessageBox.warning(
                self, "BioCLIP Quick Setup", "Confirm the upstream download notice first."
            )
            return
        model_folder_text = self._model_folder.text().strip()
        checkpoint_text = self._checkpoint.text().strip()
        taxonomy_text = self._taxonomy.text().strip()
        if self._download.isChecked() and (model_folder_text or checkpoint_text):
            QMessageBox.warning(
                self,
                "BioCLIP Quick Setup",
                "Choose either online download or a local BioCLIP folder/checkpoint, not both.",
            )
            return
        if model_folder_text and checkpoint_text:
            QMessageBox.warning(
                self,
                "BioCLIP Quick Setup",
                "Choose either a complete BioCLIP folder or a checkpoint file.",
            )
            return
        request = BioCLIPSetupRequest(
            workspace=Path(self._workspace.text().strip()),
            checkpoint=Path(checkpoint_text) if checkpoint_text else None,
            model_folder=Path(model_folder_text) if model_folder_text else None,
            download_official_checkpoint=self._download.isChecked(),
            taxonomy_csv=Path(taxonomy_text) if taxonomy_text else None,
        )
        thread = QThread(self)
        worker = _SetupWorker(self._service, request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.succeeded.connect(self._on_success)
        worker.failed.connect(self._on_failure)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._finished)
        self._thread = thread
        self._worker = worker
        self._start.setEnabled(False)
        self._cancel.setEnabled(True)
        self._close.setEnabled(False)
        self._status.setText("Starting BioCLIP setup…")
        thread.start()

    @Slot()
    def _cancel_download(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._cancel.setEnabled(False)
            self._status.setText(
                "Cancelling… The partial download will be kept and resumed next time."
            )

    @Slot(int, int, str)
    def _on_progress(self, current: int, total: int, message: str) -> None:
        self._progress.setRange(0, total)
        self._progress.setValue(current)
        if total > 10_000_000:
            self._progress.setFormat(
                f"%p%  ({current / (1024 * 1024):,.1f} / {total / (1024 * 1024):,.1f} MiB)"
            )
        else:
            self._progress.setFormat("%v / %m")
        self._status.setText(message)

    @Slot(object)
    def _on_success(self, result: object) -> None:
        if not isinstance(result, BioCLIPSetupResult):
            self._on_failure("The setup service returned an invalid result.")
            return
        details = [
            f"Model installed: {result.model_public_id}",
            f"Package: {result.model_package}",
            f"Trusted keys: {result.trusted_keys}",
        ]
        if result.taxonomy_source_public_id:
            details.append(f"Taxonomy installed: {result.taxonomy_source_public_id}")
        if result.prompt_public_id:
            details.append(f"Prompt set installed: {result.prompt_public_id}")
        if result.embedding_counts:
            details.append(
                f"Taxonomy embeddings: {result.embedding_counts[1]} written from "
                f"{result.embedding_counts[0]} labels"
            )
        if result.tree_of_life_ready:
            taxa = (
                "validated"
                if result.tree_of_life_taxa_count is None
                else f"{result.tree_of_life_taxa_count:,} taxa validated"
            )
            details.append(f"NatureAI Tree of Life: Active ({taxa})")
            if result.tree_of_life_resource_note:
                details.append(result.tree_of_life_resource_note)
        self.setup_succeeded = True
        self._status.setText(
            "Setup completed successfully. BioCLIP is loaded and ready for AI Review."
        )
        QMessageBox.information(self, "BioCLIP Quick Setup", "\n".join(details))

    @Slot(str)
    def _on_failure(self, message: str) -> None:
        self._status.setText(message)
        QMessageBox.warning(self, "BioCLIP Quick Setup", message)

    @Slot()
    def _finished(self) -> None:
        self._thread = None
        self._worker = None
        self._start.setEnabled(True)
        self._cancel.setEnabled(False)
        self._close.setEnabled(True)

    def reject(self) -> None:
        if self._thread is not None:
            QMessageBox.information(
                self,
                "BioCLIP Quick Setup",
                "Cancel the current download first. Its partial file will be retained for resume.",
            )
            return
        super().reject()
