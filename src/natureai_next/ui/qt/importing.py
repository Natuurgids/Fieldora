"""Qt import workspace backed by the production import application service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from natureai_next.ui.qt.activity import ActivityRecord, activity_center

from natureai_next.domain.importing import (
    DuplicatePolicy,
    ImportSourceKind,
    ImportStoragePolicy,
    ImportSummary,
)

try:
    from PySide6.QtCore import QObject, QSettings, QThread, Signal, Slot
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - optional GUI dependency
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


class ImportApplicationService(Protocol):
    def plan(
        self,
        roots: tuple[Path, ...],
        *,
        storage_policy: ImportStoragePolicy,
        duplicate_policy: DuplicatePolicy,
        recursive: bool = True,
        accepted_source_kinds: frozenset[ImportSourceKind] | None = None,
        cancel=None,
        progress=None,
    ) -> None: ...

    def execute(self, plan, *, cancel=None, progress=None) -> ImportSummary: ...


@dataclass(frozen=True, slots=True)
class ImportRequest:
    source: Path
    storage_policy: ImportStoragePolicy
    duplicate_policy: DuplicatePolicy
    recursive: bool
    accepted_source_kinds: frozenset[ImportSourceKind]


class _ImportWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, service: ImportApplicationService, request: ImportRequest) -> None:
        super().__init__()
        self._service = service
        self._request = request

    @Slot()
    def run(self) -> None:
        try:
            self.status.emit("Scanning, probing and hashing source files…")
            plan = self._service.plan(
                (self._request.source,),
                storage_policy=self._request.storage_policy,
                duplicate_policy=self._request.duplicate_policy,
                recursive=self._request.recursive,
                accepted_source_kinds=self._request.accepted_source_kinds,
            )
            self.status.emit(f"Importing {len(plan.items)} planned file(s)…")
            self.completed.emit(self._service.execute(plan))
        except Exception as exc:  # the application service records per-item failures
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class ImportWorkspace(QWidget):
    """Folder import UI that delegates all catalog changes to ImportService."""

    import_finished = Signal(object)

    def __init__(self, service: ImportApplicationService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._thread: QThread | None = None
        self._worker: _ImportWorker | None = None
        self._activity_record: ActivityRecord | None = None
        self._activity_summary: ImportSummary | None = None
        self._center = activity_center()
        self._center.changed.connect(self._activity_changed)

        self._source = QLineEdit()
        self._source.setReadOnly(True)
        browse = QPushButton("Choose source…")
        browse.clicked.connect(self.choose_source)
        source_row = QHBoxLayout()
        source_row.addWidget(self._source, 1)
        source_row.addWidget(browse)

        self._storage = QComboBox()
        self._storage.addItem("Create an Aperture original (managed)", ImportStoragePolicy.MANAGED.value)
        self._storage.addItem("Leave in current location (Linked)", ImportStoragePolicy.REFERENCED.value)
        self._storage.addItem("Create an Aperture original and retain source reference", ImportStoragePolicy.HYBRID.value)
        saved_policy = str(QSettings().value("import/default_storage_policy", ImportStoragePolicy.MANAGED.value))
        if saved_policy not in {policy.value for policy in ImportStoragePolicy}:
            saved_policy = ImportStoragePolicy.MANAGED.value
        saved_index = self._storage.findData(saved_policy)
        self._storage.setCurrentIndex(max(0, saved_index))
        self._storage.currentIndexChanged.connect(self._storage_policy_changed)
        self._storage_help = QLabel()
        self._storage_help.setWordWrap(True)
        self._storage_policy_changed()

        self._duplicates = QComboBox()
        self._duplicates.addItem("Skip exact duplicates", DuplicatePolicy.SKIP)
        self._duplicates.addItem(
            "Attach duplicate path to existing asset", DuplicatePolicy.ADD_FILE_INSTANCE
        )

        self._recursive = QCheckBox("Include subfolders")
        self._recursive.setChecked(True)
        self._photos = QCheckBox("Photos and RAW files")
        self._sounds = QCheckBox("Sound files")
        self._videos = QCheckBox("Video files")
        self._documents = QCheckBox("Documents")
        for option in (self._photos, self._sounds, self._videos, self._documents):
            option.setChecked(True)
        types_row = QHBoxLayout()
        types_row.addWidget(self._photos)
        types_row.addWidget(self._sounds)
        types_row.addWidget(self._videos)
        types_row.addWidget(self._documents)

        form = QFormLayout()
        form.addRow("Source", source_row)
        form.addRow("Original handling", self._storage)
        form.addRow("", self._storage_help)
        form.addRow("Duplicates", self._duplicates)
        form.addRow("Import", types_row)
        form.addRow("", self._recursive)

        self._start = QPushButton("Start import")
        self._start.setEnabled(False)
        self._start.clicked.connect(self.start_import)
        self._status = QLabel("Choose a folder containing photos, sounds, videos or documents.")
        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._start)
        layout.addWidget(self._status)
        layout.addWidget(self._details, 1)


    def _current_storage_policy(self) -> ImportStoragePolicy:
        """Return the selected policy regardless of Qt QVariant conversion."""
        value = self._storage.currentData()
        try:
            return ImportStoragePolicy(str(value))
        except (TypeError, ValueError):
            return ImportStoragePolicy.MANAGED

    @Slot(int)
    def _storage_policy_changed(self, _index: int = -1) -> None:
        policy = self._current_storage_policy()
        QSettings().setValue("import/default_storage_policy", policy.value)
        descriptions = {
            ImportStoragePolicy.MANAGED: "Copies the source into Aperture-managed storage. Best for portable libraries and reliable backups, but uses additional disk space.",
            ImportStoragePolicy.REFERENCED: "Keeps the full-size original where it is and stores only catalog data, thumbnails and enrichments in Aperture. The source must remain accessible.",
            ImportStoragePolicy.HYBRID: "Creates a managed Aperture original and also records the source location for provenance and relinking.",
        }
        self._storage_help.setText(descriptions[policy])

    @Slot()
    def choose_source(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Choose media folder", self._source.text()
        )
        if selected:
            self.set_source(Path(selected))

    # Kept as a compatibility alias for existing callers and shortcuts.
    choose_folder = choose_source

    def set_source(self, source: Path) -> None:
        self._source.setText(str(source))
        self._start.setEnabled(source.is_dir() and self._thread is None)

    @Slot()
    def start_import(self) -> None:
        source = Path(self._source.text())
        if not source.is_dir():
            QMessageBox.warning(self, "Import", "Choose an existing media folder first.")
            return
        accepted_source_kinds = self._selected_source_kinds()
        if not accepted_source_kinds:
            QMessageBox.warning(self, "Import", "Select at least one type of media to import.")
            return
        request = ImportRequest(
            source=source,
            storage_policy=self._current_storage_policy(),
            duplicate_policy=self._duplicates.currentData(),
            recursive=self._recursive.isChecked(),
            accepted_source_kinds=accepted_source_kinds,
        )
        self._set_busy(True)
        self._details.clear()
        self._activity_summary = None

        def operation(progress, cancelled):
            progress(0, 0, "Scanning source folders…")
            plan = self._service.plan(
                (request.source,),
                storage_policy=request.storage_policy,
                duplicate_policy=request.duplicate_policy,
                recursive=request.recursive,
                accepted_source_kinds=request.accepted_source_kinds,
                cancel=(lambda: (_ for _ in ()).throw(InterruptedError()) if cancelled() else None),
                progress=progress,
            )
            progress(0, len(plan.items), f"Importing {len(plan.items)} planned file(s)…")
            summary = self._service.execute(
                plan,
                cancel=(lambda: (_ for _ in ()).throw(InterruptedError()) if cancelled() else None),
                progress=progress,
            )
            self._activity_summary = summary
            progress(len(plan.items), len(plan.items), "Import complete")
            return (
                f"{summary.imported} imported, {summary.attached} attached, "
                f"{summary.skipped} skipped, {summary.failed} failed."
            )

        self._activity_record = self._center.start(
            "Import media",
            str(request.source),
            operation,
            kind="import.media",
            payload={"source": str(request.source), "storage_policy": request.storage_policy.value},
        )
        self._status.setText("Import queued in Activity Center…")

    @Slot()
    def _activity_changed(self) -> None:
        record = self._activity_record
        if record is None:
            return
        self._status.setText(record.message)
        if record.state == "completed":
            summary = self._activity_summary
            self._activity_record = None
            self._set_busy(False)
            if summary is not None:
                self._on_completed(summary)
        elif record.state in {"failed", "cancelled"}:
            message = record.technical_detail or record.message
            self._activity_record = None
            self._set_busy(False)
            self._on_failed(message)

    @Slot(object)
    def _on_completed(self, summary: ImportSummary) -> None:
        self._status.setText(
            f"Completed: {summary.imported} imported, {summary.attached} attached, "
            f"{summary.skipped} skipped, {summary.failed} failed."
        )
        lines = [
            f"Total: {summary.total}",
            f"Imported: {summary.imported}",
            f"Attached: {summary.attached}",
            f"Skipped: {summary.skipped}",
            f"Failed: {summary.failed}",
        ]
        for result in summary.results:
            if result.state == "failed":
                lines.append(
                    f"FAILED {result.source_path or result.item_key}: {result.error_code or 'unknown error'}"
                )
        self._details.setPlainText("\n".join(lines))
        self.import_finished.emit(summary)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._status.setText("Import planning failed.")
        self._details.setPlainText(message)
        QMessageBox.critical(self, "Import failed", message)

    @Slot()
    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._start.setEnabled(not busy and Path(self._source.text()).is_dir())
        self._storage.setEnabled(not busy)
        self._duplicates.setEnabled(not busy)
        for option in (self._photos, self._sounds, self._videos, self._documents):
            option.setEnabled(not busy)
        self._recursive.setEnabled(not busy)

    def _selected_source_kinds(self) -> frozenset[ImportSourceKind]:
        kinds: set[ImportSourceKind] = set()
        if self._photos.isChecked():
            kinds.update({ImportSourceKind.PHOTO, ImportSourceKind.RAW_PHOTO})
        if self._sounds.isChecked():
            kinds.add(ImportSourceKind.SOUND)
        if self._videos.isChecked():
            kinds.add(ImportSourceKind.VIDEO)
        if self._documents.isChecked():
            kinds.add(ImportSourceKind.DOCUMENT)
        return frozenset(kinds)
