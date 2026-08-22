"""Application-wide durable background activity tracking for long-running Qt work."""

from __future__ import annotations

import inspect
import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from platformdirs import user_state_dir

try:
    from PySide6.QtCore import QObject, QThread, Signal, Slot
    from PySide6.QtWidgets import (
        QDialog,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QProgressBar,
        QPushButton,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required") from exc


class ActivityCancelled(RuntimeError):
    """Raised cooperatively when a user cancels a background activity."""


@dataclass
class ActivityRecord:
    title: str
    detail: str
    state: str = "queued"
    current: int = 0
    total: int = 0
    message: str = "Queued"
    started_at: str = ""
    finished_at: str = ""
    result: str = ""
    activity_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = "generic"
    payload: dict[str, object] = field(default_factory=dict)
    technical_detail: str = ""
    recommended_action: str = ""


class _Worker(QObject):
    progressed = Signal(object, int, int, str)
    succeeded = Signal(object, object)
    failed = Signal(object, str)
    cancelled = Signal(object)
    finished = Signal()

    def __init__(
        self,
        record: ActivityRecord,
        operation: Callable[..., object],
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self._record = record
        self._operation = operation
        self._cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        try:

            def progress(c, t, m):
                return self.progressed.emit(self._record, c, t, m)

            if len(inspect.signature(self._operation).parameters) >= 2:
                result = self._operation(progress, self._cancel_event.is_set)
            else:
                result = self._operation(progress)
            if self._cancel_event.is_set():
                raise ActivityCancelled("Cancelled by user")
        except (ActivityCancelled, InterruptedError):
            self.cancelled.emit(self._record)
        except Exception as exc:
            self.failed.emit(self._record, str(exc))
        else:
            self.succeeded.emit(self._record, result)
        finally:
            self.finished.emit()


class ActivityCenter(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._state_path = Path(user_state_dir("NatureAI Next", "NatureAI")) / "activity.json"
        self._threads: dict[str, QThread] = {}
        self._workers: dict[str, _Worker] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._operations: dict[str, Callable[..., object]] = {}
        self._recovery_factories: dict[
            str, Callable[[dict[str, object]], Callable[..., object]]
        ] = {
            "gbif-taxonomy-import": self._detached_taxonomy_recovery,
        }
        self._last_progress_emit: dict[str, float] = {}
        cpu_count = max(1, os.cpu_count() or 1)
        self._default_concurrency = max(2, min(8, max(2, cpu_count - 1)))
        self._kind_concurrency: dict[str, int] = {
            # Map preparation is network-, disk-, memory-, and CPU-intensive.
            # Keep a small bounded pool while still allowing useful parallelism.
            "offline-map.prepare": max(2, min(4, cpu_count // 2 or 1)),
            "export.package": max(2, min(4, cpu_count // 2 or 1)),
            "export.data": max(2, min(4, cpu_count // 2 or 1)),
            "report.generate": max(2, min(4, cpu_count // 2 or 1)),
            # Library-mutating/import and backup operations are serialized per kind.
            "import.media": 1,
            "backup.library": 1,
            "storage.verify": 1,
            # Detached taxonomy imports are deliberately serialized.
            "gbif-taxonomy-import": 1,
        }
        self.records: list[ActivityRecord] = self._load()

    @staticmethod
    def _detached_taxonomy_recovery(payload: dict[str, object]) -> Callable[..., object]:
        source = Path(str(payload["source"]))

        def operation(progress, cancelled) -> str:
            from natureai_next.application.dwca_taxonomy import run_dwca_taxonomy_import_isolated

            result = run_dwca_taxonomy_import_isolated(
                source, progress=progress, cancelled=cancelled
            )
            return (
                f"Published isolated GBIF taxonomy source {result.source_public_id}: "
                f"{result.taxa_count:,} taxa and {result.names_count:,} names. "
                f"Independent database: {result.package_path}"
            )

        return operation

    @staticmethod
    def _reconcile_detached_record(record: ActivityRecord) -> None:
        if record.kind != "gbif-taxonomy-import":
            return
        source_value = record.payload.get("source")
        if not source_value:
            return
        try:
            from natureai_next.application.dwca_taxonomy import detached_taxonomy_job_state

            state = detached_taxonomy_job_state(Path(str(source_value)))
        except Exception:
            return
        if state.get("state") == "ready":
            record.state = "completed"
            record.current = int(state.get("current", 100))
            record.total = int(state.get("total", 100))
            record.message = "Completed"
            record.finished_at = str(
                state.get("finished_at") or datetime.now().isoformat(timespec="seconds")
            )
            record.result = (
                f"Published isolated GBIF taxonomy source {state.get('source_public_id', '')}: "
                f"{int(state.get('taxa_count', 0)):,} taxa and {int(state.get('names_count', 0)):,} names. "
                f"Independent database: {state.get('package_path', '')}"
            )
        elif state.get("state") == "running":
            record.state = "interrupted"
            record.current = int(state.get("current", record.current))
            record.total = int(state.get("total", record.total or 100))
            record.message = (
                "Detached taxonomy build is still running. Choose Resume / Retry to reattach."
            )
            record.finished_at = ""

    def _load(self) -> list[ActivityRecord]:
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return []
        records: list[ActivityRecord] = []
        for item in raw if isinstance(raw, list) else []:
            try:
                record = ActivityRecord(**item)
            except TypeError:
                continue
            if record.state in {"running", "cancelling", "queued"}:
                record.state = "interrupted"
                record.message = "Interrupted when NatureAI stopped. Resume or retry is available."
                record.finished_at = datetime.now().isoformat(timespec="seconds")
            self._reconcile_detached_record(record)
            records.append(record)
        return records[:100]

    def _save(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._state_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps([asdict(r) for r in self.records[:100]], indent=2), encoding="utf-8"
        )
        temp.replace(self._state_path)

    @property
    def running_count(self) -> int:
        return sum(1 for item in self.records if item.state in {"running", "cancelling"})

    def register_recovery(
        self, kind: str, factory: Callable[[dict[str, object]], Callable[..., object]]
    ) -> None:
        self._recovery_factories[kind] = factory
        self.changed.emit()

    def start(
        self,
        title: str,
        detail: str,
        operation: Callable[..., object],
        *,
        kind: str = "generic",
        payload: dict[str, object] | None = None,
    ) -> ActivityRecord:
        record = ActivityRecord(
            title=title,
            detail=detail,
            state="queued",
            message="Queued — waiting for an available worker…",
            kind=kind,
            payload=dict(payload or {}),
        )
        self.records.insert(0, record)
        self._operations[record.activity_id] = operation
        self._save()
        self.changed.emit()
        self._schedule()
        return record

    def _limit_for(self, kind: str) -> int:
        return self._kind_concurrency.get(kind, self._default_concurrency)

    def _running_for(self, kind: str) -> int:
        return sum(
            1
            for item in self.records
            if item.kind == kind and item.state in {"running", "cancelling"}
        )

    def _schedule(self) -> None:
        """Promote queued activities only when their module worker budget permits."""
        launched = False
        # Oldest queued work starts first; records are stored newest-first.
        for record in reversed(self.records):
            if record.state != "queued":
                continue
            if self._running_for(record.kind) >= self._limit_for(record.kind):
                continue
            operation = self._operations.get(record.activity_id)
            if operation is None:
                continue
            record.state = "running"
            record.message = "Starting…"
            record.started_at = datetime.now().isoformat(timespec="seconds")
            self._launch(record, operation, notify=False)
            launched = True
        if launched:
            self._save()
            self.changed.emit()

    def _launch(
        self, record: ActivityRecord, operation: Callable[..., object], *, notify: bool = True
    ) -> None:
        cancel_event = threading.Event()
        thread = QThread(self)
        worker = _Worker(record, operation, cancel_event)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progressed.connect(self._progress)
        worker.succeeded.connect(self._success)
        worker.failed.connect(self._failure)
        worker.cancelled.connect(self._cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda activity_id=record.activity_id: self._cleanup(activity_id))
        self._threads[record.activity_id] = thread
        self._workers[record.activity_id] = worker
        self._cancel_events[record.activity_id] = cancel_event
        if notify:
            self._save()
            self.changed.emit()
        thread.start()

    def cancel(self, record: ActivityRecord) -> None:
        if record.state == "queued":
            record.state = "cancelled"
            record.message = "Cancelled before the activity started."
            record.finished_at = datetime.now().isoformat(timespec="seconds")
            self._save()
            self.changed.emit()
            return
        event = self._cancel_events.get(record.activity_id)
        if event is None or record.state not in {"running", "cancelling"}:
            return
        event.set()
        record.state = "cancelling"
        record.message = "Cancelling at the next safe checkpoint…"
        self._save()
        self.changed.emit()

    def cancel_all(self) -> None:
        for record in list(self.records):
            self.cancel(record)

    def retry(self, record: ActivityRecord) -> bool:
        if record.state not in {"failed", "cancelled", "interrupted"}:
            return False
        operation = self._operations.get(record.activity_id)
        if operation is None:
            factory = self._recovery_factories.get(record.kind)
            if factory is None:
                return False
            operation = factory(record.payload)
            self._operations[record.activity_id] = operation
        record.state = "queued"
        record.message = "Queued to resume from the last safe checkpoint…"
        record.started_at = ""
        record.finished_at = ""
        record.technical_detail = ""
        record.recommended_action = ""
        record.result = ""
        self._save()
        self.changed.emit()
        self._schedule()
        return True

    def can_retry(self, record: ActivityRecord) -> bool:
        return record.state in {"failed", "cancelled", "interrupted"} and (
            record.activity_id in self._operations or record.kind in self._recovery_factories
        )

    @Slot(object, int, int, str)
    def _progress(self, record: ActivityRecord, current: int, total: int, message: str) -> None:
        record.current = current
        record.total = total
        record.message = message
        now = time.monotonic()
        last = self._last_progress_emit.get(record.activity_id, 0.0)
        # Keep worker progress unrestricted but persist/refresh the UI at most
        # once per second, plus phase boundaries and completion.
        boundary = current in {0, total}
        if boundary or now - last >= 1.0:
            self._last_progress_emit[record.activity_id] = now
            self._save()
            self.changed.emit()

    @Slot(object, object)
    def _success(self, record: ActivityRecord, result: object) -> None:
        record.state = "completed"
        record.current = max(record.current, record.total)
        record.message = "Completed"
        record.finished_at = datetime.now().isoformat(timespec="seconds")
        record.result = str(result)
        self._save()
        self.changed.emit()

    @staticmethod
    def _logical_error(message: str) -> tuple[str, str]:
        lowered = message.casefold()
        if "unique constraint failed: taxa.public_id" in lowered:
            return (
                "The taxonomy update found records that are already installed. Your current taxonomy is still available.",
                "Resume the repaired installation. The verified download does not need to be downloaded again.",
            )
        if "database is locked" in lowered:
            return (
                "Aperture could not finish the database step because another operation was using the library.",
                "Wait for other work to finish, then choose Resume / Retry.",
            )
        if "checksum" in lowered or "verification" in lowered:
            return (
                "The downloaded resource could not be verified and was not installed.",
                "Retry the download. Your currently installed data remains unchanged.",
            )
        return (
            "The operation could not be completed. Existing installed data remains available where possible.",
            "Open Technical details, correct the reported cause, then choose Resume / Retry.",
        )

    @Slot(object, str)
    def _failure(self, record: ActivityRecord, message: str) -> None:
        logical, action = self._logical_error(message)
        record.state = "failed"
        record.message = logical
        record.technical_detail = message
        record.recommended_action = action
        record.finished_at = datetime.now().isoformat(timespec="seconds")
        self._save()
        self.changed.emit()

    def open_tasks(self) -> tuple[ActivityRecord, ...]:
        """Return authoritative resumable/in-flight work independent of history cleanup."""
        return tuple(
            r
            for r in self.records
            if (r.state in {"failed", "cancelled"} and self.can_retry(r))
            or r.state in {"queued", "running", "cancelling", "interrupted"}
        )

    def clean_finished(self) -> int:
        # Cleaning the Activity Center is history cleanup only. Never remove
        # interrupted, failed, cancelled, queued, or running work because those
        # records are the durable resume handles for map and taxonomy processing.
        removable = {"completed", "archived"}
        before = len(self.records)
        self.records[:] = [r for r in self.records if r.state not in removable]
        removed = before - len(self.records)
        if removed:
            self._save()
            self.changed.emit()
        return removed

    @Slot(object)
    def _cancelled(self, record: ActivityRecord) -> None:
        record.state = "cancelled"
        record.message = "Cancelled. Partial downloads and checkpoints were preserved."
        record.finished_at = datetime.now().isoformat(timespec="seconds")
        self._save()
        self.changed.emit()

    def _cleanup(self, activity_id: str) -> None:
        self._threads.pop(activity_id, None)
        self._workers.pop(activity_id, None)
        self._cancel_events.pop(activity_id, None)
        self._last_progress_emit.pop(activity_id, None)
        self._save()
        self.changed.emit()
        self._schedule()


_CENTER: ActivityCenter | None = None


def activity_center() -> ActivityCenter:
    global _CENTER
    if _CENTER is None:
        _CENTER = ActivityCenter()
    return _CENTER


class ActivityCenterWidget(QWidget):
    """Reusable Operations Center content for the main workspace and dialog."""

    def __init__(self, parent: QWidget | None = None, *, show_close: bool = False) -> None:
        super().__init__(parent)
        self._center = activity_center()
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._selection_changed)
        self._title = QLabel("No background activity")
        self._title.setWordWrap(True)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._details = QTextBrowser()
        self._cancel = QPushButton("Cancel task")
        self._retry = QPushButton("Resume / Retry")
        self._clean = QPushButton("Clean finished")
        self._cancel.clicked.connect(self._cancel_selected)
        self._retry.clicked.connect(self._retry_selected)
        self._clean.clicked.connect(self._center.clean_finished)
        layout = QVBoxLayout(self)
        heading = QLabel(
            "<h2>Operations Center</h2>"
            "<p>Monitor background jobs, resumable processing, failures, and system notifications.</p>"
        )
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._title)
        layout.addWidget(self._progress)
        layout.addWidget(self._details, 1)
        row = QHBoxLayout()
        row.addWidget(self._cancel)
        row.addWidget(self._retry)
        row.addWidget(self._clean)
        row.addStretch(1)
        if show_close:
            close = QPushButton("Close")
            close.clicked.connect(self.window().close)
            row.addWidget(close)
        layout.addLayout(row)
        self._center.changed.connect(self.refresh)
        self.refresh()

    def _selected(self) -> ActivityRecord | None:
        row = self._list.currentRow()
        return self._center.records[row] if 0 <= row < len(self._center.records) else None

    @Slot()
    def _cancel_selected(self) -> None:
        record = self._selected()
        if record is not None:
            self._center.cancel(record)

    @Slot()
    def _retry_selected(self) -> None:
        record = self._selected()
        if record is not None:
            self._center.retry(record)

    @Slot()
    def refresh(self) -> None:
        selected = self._list.currentRow()
        open_count = len(self._center.open_tasks())
        self._summary.setText(
            f"Open Tasks: {open_count}. Running and resumable work is retained even when finished history is cleaned."
        )
        self._list.clear()
        for record in self._center.records:
            marker = {
                "running": "▶",
                "cancelling": "◼",
                "completed": "✓",
                "failed": "⚠",
                "cancelled": "■",
                "interrupted": "↻",
            }.get(record.state, "○")
            self._list.addItem(QListWidgetItem(f"{marker} {record.title} — {record.message}"))
        if self._list.count():
            self._list.setCurrentRow(min(max(selected, 0), self._list.count() - 1))
        else:
            self._selection_changed(-1)

    @Slot(int)
    def _selection_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._center.records):
            self._title.setText("No background activity")
            self._progress.setValue(0)
            self._details.clear()
            self._cancel.setEnabled(False)
            self._retry.setEnabled(False)
            return
        record = self._center.records[row]
        self._title.setText(f"<b>{record.title}</b><br>{record.detail}<br>{record.message}")
        percent = (
            int(record.current * 100 / record.total)
            if record.total
            else (100 if record.state == "completed" else 0)
        )
        self._progress.setValue(max(0, min(percent, 100)))
        self._details.setPlainText(
            f"State: {record.state}\nStarted: {record.started_at or '-'}\nFinished: {record.finished_at or '-'}\n"
            f"Progress: {record.current} / {record.total or '?'}\n\n{record.result or record.message}"
            + (
                f"\n\nRecommended action:\n{record.recommended_action}"
                if record.recommended_action
                else ""
            )
            + (
                f"\n\nTechnical details:\n{record.technical_detail}"
                if record.technical_detail
                else ""
            )
        )
        self._cancel.setEnabled(record.state in {"running", "cancelling"})
        self._retry.setEnabled(self._center.can_retry(record))


class ActivityCenterDialog(QDialog):
    """Compatibility dialog using the same Operations Center content."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Operations Center")
        self.resize(860, 600)
        layout = QVBoxLayout(self)
        content = ActivityCenterWidget(self)
        layout.addWidget(content)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
