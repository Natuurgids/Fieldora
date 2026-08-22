"""Independent Knowledge Base workspace for AI review and taxonomy enrichment."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from time import perf_counter

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QSettings,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QTextBrowser,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class _KnowledgeQueryWorker(QObject):
    """Thread-confined read worker for the Library knowledge projection."""

    succeeded = Signal(int, object)
    failed = Signal(int, str)
    finished = Signal()

    def __init__(
        self, generation: int, database: Path, query: str, provider: str, state: str
    ) -> None:
        super().__init__()
        self._generation = generation
        self._database = Path(database)
        self._query = query.casefold()
        self._provider = provider
        self._state = state

    def _connect(self) -> sqlite3.Connection:
        # A navigation request must never queue behind a writer. WAL readers
        # normally proceed independently; a very short timeout converts an
        # exceptional lock into a retryable UI status instead of a frozen UI.
        connection = sqlite3.connect(
            f"file:{self._database.as_posix()}?mode=ro",
            uri=True,
            timeout=0.075,
            isolation_level=None,
            check_same_thread=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=75")
        return connection

    @staticmethod
    def _tables(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    @Slot()
    def run(self) -> None:
        rows: list[tuple[str, ...]] = []
        try:
            with self._connect() as connection:
                tables = self._tables(connection)
                if "ai_suggestions" in tables:
                    sql = """
                        SELECT COALESCE(fi.normalized_path,a.title,a.public_id) photo,
                               COALESCE(s.candidate_label,t.scientific_name,'Unlabelled suggestion') label,
                               COALESCE(s.calibrated_score,s.raw_score) confidence,
                               s.review_state state, COALESCE(s.taxonomic_level,t.rank,'') rank,
                               COALESCE(mp.model_identity,'BioCLIP') source,
                               COALESCE(s.reviewed_at_us,s.created_at_us,0) updated
                        FROM ai_suggestions s
                        LEFT JOIN assets a ON a.id=s.asset_id
                        LEFT JOIN file_instances fi ON fi.id=a.primary_file_instance_id
                        LEFT JOIN taxa t ON t.id=s.candidate_taxon_id
                        LEFT JOIN inference_runs ir ON ir.id=s.inference_run_id
                        LEFT JOIN model_variants mv ON mv.id=ir.model_variant_id
                        LEFT JOIN model_packages mp ON mp.id=mv.package_id
                        ORDER BY updated DESC LIMIT 2500
                    """
                    for item in connection.execute(sql):
                        candidate = " ".join(str(item[key] or "") for key in item).casefold()
                        if (
                            self._provider == "GBIF"
                            or (self._state != "All states" and item["state"] != self._state)
                            or (self._query and self._query not in candidate)
                        ):
                            continue
                        score = (
                            "" if item["confidence"] is None else f"{float(item['confidence']):.3f}"
                        )
                        rows.append(
                            (
                                str(item["photo"] or ""),
                                "BioCLIP",
                                str(item["label"] or ""),
                                score,
                                str(item["state"] or ""),
                                str(item["rank"] or ""),
                                str(item["source"] or "BioCLIP"),
                                str(item["updated"] or ""),
                            )
                        )
                if "asset_taxonomy_enrichments" in tables and self._state in (
                    "All states",
                    "accepted",
                ):
                    sql = """
                        SELECT COALESCE(fi.normalized_path,a.title,a.public_id) photo,
                               e.scientific_name,COALESCE(e.vernacular_name,'') vernacular,
                               COALESCE(e.rank,'') rank,e.source_key,e.source_database_identity,e.modified_at_us
                        FROM asset_taxonomy_enrichments e
                        JOIN assets a ON a.id=e.asset_id
                        LEFT JOIN file_instances fi ON fi.id=a.primary_file_instance_id
                        ORDER BY e.modified_at_us DESC LIMIT 2500
                    """
                    for item in connection.execute(sql):
                        candidate = " ".join(str(item[key] or "") for key in item).casefold()
                        if self._provider == "BioCLIP" or (
                            self._query and self._query not in candidate
                        ):
                            continue
                        label = str(item["scientific_name"] or "")
                        if item["vernacular"]:
                            label += f" — {item['vernacular']}"
                        rows.append(
                            (
                                str(item["photo"] or ""),
                                str(item["source_key"] or "GBIF").upper(),
                                label,
                                "",
                                "accepted",
                                str(item["rank"] or ""),
                                str(item["source_database_identity"] or ""),
                                str(item["modified_at_us"] or ""),
                            )
                        )
            rows.sort(key=lambda row: row[7], reverse=True)
            self.succeeded.emit(self._generation, rows)
        except Exception as exc:
            self.failed.emit(self._generation, str(exc))
        finally:
            self.finished.emit()


class _KnowledgeTableModel(QAbstractTableModel):
    """Zero-copy projection model for knowledge rows.

    QTableWidget creates one QObject-backed item per cell and repeatedly asks
    ResizeToContents columns to remeasure them.  For 2,500 rows that means
    20,000 item allocations on the GUI thread.  A table model exposes the
    immutable row tuples directly and makes replacing a result set O(1).
    """

    HEADERS = (
        "Photo",
        "Provider",
        "Prediction / taxon",
        "Confidence",
        "State",
        "Rank",
        "Source / model",
        "Updated",
    )

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[tuple[str, ...]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        try:
            return self._rows[index.row()][index.column()]
        except IndexError:
            return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section] if 0 <= section < len(self.HEADERS) else None
        return super().headerData(section, orientation, role)

    def replace_rows(self, rows: list[tuple[str, ...]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class KnowledgeDataView(QWidget):
    """Searchable read-only cross-provider view that never blocks navigation."""

    def __init__(self, library_database: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._database = Path(library_database)
        self._generation = 0
        self._threads: set[QThread] = set()
        self._workers: set[_KnowledgeQueryWorker] = set()
        self._query_active = False
        self._refresh_pending = False
        self._loaded_once = False
        self._query_started_at = 0.0
        self._search = QLineEdit()
        self._search.setPlaceholderText(
            "Search filename, AI prediction, scientific name, common name, provider, or state…"
        )
        self._provider = QComboBox()
        self._provider.addItems(("All providers", "BioCLIP", "GBIF"))
        self._state = QComboBox()
        self._state.addItems(
            ("All states", "pending", "deferred", "accepted", "rejected", "superseded")
        )
        self._model = _KnowledgeTableModel(self)
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(False)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 90), (3, 90), (4, 90), (5, 90), (6, 170), (7, 140)):
            self._table.setColumnWidth(column, width)
        self._status = QLabel(
            "Knowledge data is read independently from the active Library database."
        )
        self._status.setWordWrap(True)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        row = QHBoxLayout()
        row.addWidget(self._search, 1)
        row.addWidget(self._provider)
        row.addWidget(self._state)
        row.addWidget(refresh)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._status)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self.refresh)
        self._search.textChanged.connect(lambda _text: self._timer.start())
        self._provider.currentTextChanged.connect(lambda _text: self.refresh())
        self._state.currentTextChanged.connect(lambda _text: self.refresh())

    @Slot()
    def refresh(self) -> None:
        # Coalesce repeated activation/filter events.  The old implementation
        # could run two full queries when the workspace first opened and many
        # concurrent queries while typing.
        if self._query_active:
            self._refresh_pending = True
            return
        self._start_refresh()

    def _start_refresh(self) -> None:
        self._generation += 1
        generation = self._generation
        self._refresh_pending = False
        if not self._database.is_file():
            self._model.replace_rows([])
            self._status.setText("The active Library database is not available.")
            return
        self._query_active = True
        self._query_started_at = perf_counter()
        self._status.setText("Loading knowledge independently…")
        thread = QThread(self)
        worker = _KnowledgeQueryWorker(
            generation,
            self._database,
            self._search.text().strip(),
            self._provider.currentText(),
            self._state.currentText(),
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._query_succeeded)
        worker.failed.connect(self._query_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._release_worker(t, w))
        self._threads.add(thread)
        self._workers.add(worker)
        thread.start()

    @Slot(int, object)
    def _query_succeeded(self, generation: int, rows: object) -> None:
        if generation != self._generation:
            return
        result_rows = rows if isinstance(rows, list) else []
        self._model.replace_rows(result_rows)
        self._loaded_once = True
        elapsed_ms = (perf_counter() - self._query_started_at) * 1000.0
        self._status.setText(
            f"{len(result_rows):,} knowledge record(s) shown in {elapsed_ms:,.0f} ms • BioCLIP and GBIF remain independent providers."
        )

    @Slot(int, str)
    def _query_failed(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self._model.replace_rows([])
        if "locked" in message.casefold() or "busy" in message.casefold():
            self._status.setText(
                "Knowledge is temporarily busy. Library navigation remains available; choose Refresh to retry."
            )
        else:
            self._status.setText(f"Knowledge search unavailable: {message}")

    def _release_worker(self, thread: QThread, worker: _KnowledgeQueryWorker) -> None:
        self._threads.discard(thread)
        self._workers.discard(worker)
        self._query_active = False
        if self._refresh_pending:
            QTimer.singleShot(0, self._start_refresh)


class _CanonicalReviewWorker(QObject):
    succeeded = Signal(int, object)
    failed = Signal(int, str)
    finished = Signal()

    def __init__(
        self,
        generation: int,
        database: Path,
        subject_type: str | None,
        state: str,
        query: str,
        assigned_to: str,
    ) -> None:
        super().__init__()
        self._generation = generation
        self._database = Path(database)
        self._subject_type = subject_type
        self._state = state
        self._query = query.casefold()
        self._assigned_to = assigned_to.strip()

    @Slot()
    def run(self) -> None:
        try:
            if not self._database.is_file():
                self.succeeded.emit(self._generation, [])
                return
            connection = sqlite3.connect(
                f"file:{self._database.as_posix()}?mode=ro",
                uri=True,
                timeout=0.075,
                isolation_level=None,
                check_same_thread=True,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA busy_timeout=75")
            where: list[str] = []
            parameters: list[object] = []
            if self._subject_type:
                where.append("subject_type=?")
                parameters.append(self._subject_type)
            if self._state != "All states":
                where.append("status=?")
                parameters.append(self._state)
            clause = " WHERE " + " AND ".join(where) if where else ""
            has_assignments = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='enrichment_review_assignments'"
            ).fetchone() is not None
            assignment_columns = (
                ",COALESCE(a.assigned_to,'') assigned_to,"
                "COALESCE(a.assigned_by,'') assigned_by,"
                "COALESCE(a.note,'') assignment_note"
                if has_assignments
                else ",'' assigned_to,'' assigned_by,'' assignment_note"
            )
            assignment_join = (
                " LEFT JOIN enrichment_review_assignments a ON a.enrichment_id=enrichment_records.enrichment_id"
                if has_assignments
                else ""
            )
            if self._assigned_to == "Unassigned":
                where.append(
                    "NOT EXISTS(SELECT 1 FROM enrichment_review_assignments qa "
                    "WHERE qa.enrichment_id=enrichment_records.enrichment_id)"
                    if has_assignments else "1=1"
                )
            elif self._assigned_to and self._assigned_to != "All assignees":
                where.append(
                    "EXISTS(SELECT 1 FROM enrichment_review_assignments qa "
                    "WHERE qa.enrichment_id=enrichment_records.enrichment_id AND qa.assigned_to=?)"
                    if has_assignments else "1=0"
                )
                if has_assignments:
                    parameters.append(self._assigned_to)
            clause = " WHERE " + " AND ".join(where) if where else ""
            sql = (
                "SELECT enrichment_records.enrichment_id AS enrichment_id,subject_type,subject_public_id,enrichment_type,"
                "producer_id,COALESCE(producer_version,'' ) producer_version,"
                "COALESCE(producer_run_id,'' ) producer_run_id,status,confidence,"
                "COALESCE(summary,'' ) summary,payload_json,COALESCE(evidence_json,'' ) evidence_json,"
                "source_snapshot_json,created_at_us,updated_at_us,reviewed_at_us,COALESCE(reviewer,'' ) reviewer"
                + assignment_columns
                + " FROM enrichment_records" + assignment_join + clause
                + " ORDER BY updated_at_us DESC LIMIT 2500"
            )
            rows: list[dict[str, object]] = []
            for row in connection.execute(sql, parameters):
                item = dict(row)
                searchable = " ".join(str(value or "") for value in item.values()).casefold()
                if self._query and self._query not in searchable:
                    continue
                rows.append(item)
            connection.close()
            self.succeeded.emit(self._generation, rows)
        except Exception as exc:
            self.failed.emit(self._generation, str(exc))
        finally:
            self.finished.emit()


class _CanonicalReviewModel(QAbstractTableModel):
    HEADERS = ("Subject", "Enrichment", "Producer", "Confidence", "State", "Assigned to", "Summary", "Updated")
    KEYS = (
        "subject_public_id",
        "enrichment_type",
        "producer_id",
        "confidence",
        "status",
        "assigned_to",
        "summary",
        "updated_at_us",
    )

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, object]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        row = self._rows[index.row()]
        value = row.get(self.KEYS[index.column()])
        if self.KEYS[index.column()] == "confidence":
            return "" if value is None else f"{float(value):.3f}"
        return "" if value is None else str(value)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section] if 0 <= section < len(self.HEADERS) else None
        return super().headerData(section, orientation, role)

    def replace_rows(self, rows: list[dict[str, object]]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row(self, index: int) -> dict[str, object] | None:
        return self._rows[index] if 0 <= index < len(self._rows) else None


class CanonicalMediaReview(QWidget):
    """Producer-neutral review queue for sound, video and document enrichment."""

    def __init__(
        self,
        *,
        media_name: str,
        subject_type: str | None,
        database: Path,
        controller: object | None = None,
        initial_state: str = "All states",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._media_name = media_name
        self._subject_type = subject_type
        self._database = Path(database)
        self._controller = controller
        self._generation = 0
        self._thread: QThread | None = None
        self._worker: _CanonicalReviewWorker | None = None
        self._model = _CanonicalReviewModel(self)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search subject, producer, result, state, or summary…")
        self._state = QComboBox()
        self._state.addItems(
            ("All states", "pending_review", "generated", "accepted", "rejected", "superseded", "expired")
        )
        state_index = self._state.findText(initial_state)
        if state_index >= 0:
            self._state.setCurrentIndex(state_index)
        self._assignee = QComboBox()
        self._assignee.setEditable(True)
        self._assignee.addItems(("All assignees", "Unassigned"))
        self._assignee.setToolTip(
            "Choose an identity ID to see that user's queue, or type one and press Enter."
        )
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._table.clicked.connect(self._show_selected)
        self._detail = QTextBrowser()
        self._detail.setHtml(
            f"<h3>{media_name} review</h3><p>Select a reviewable enrichment result.</p>"
        )
        self._status = QLabel()
        self._status.setWordWrap(True)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        self._accept = QPushButton("Accept")
        self._reject = QPushButton("Reject")
        self._assign = QPushButton("Defer to user…")
        self._unassign = QPushButton("Return to shared queue")
        self._accept.clicked.connect(lambda: self._review("accept"))
        self._reject.clicked.connect(lambda: self._review("reject"))
        self._assign.clicked.connect(self._assign_selected)
        self._unassign.clicked.connect(lambda: self._set_assignment(None))
        self._accept.setEnabled(False)
        self._reject.setEnabled(False)
        self._assign.setEnabled(False)
        self._unassign.setEnabled(False)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("State"))
        filters.addWidget(self._state)
        filters.addWidget(QLabel("Assigned"))
        filters.addWidget(self._assignee)
        filters.addWidget(self._search, 1)
        filters.addWidget(refresh)
        actions = QHBoxLayout()
        actions.addWidget(self._accept)
        actions.addWidget(self._reject)
        actions.addWidget(self._assign)
        actions.addWidget(self._unassign)
        actions.addStretch(1)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._table)
        splitter.addWidget(self._detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<h2>{media_name} AI Review</h2>"))
        intro = QLabel(
            f"Review canonical {media_name.casefold()} enrichment produced by compatible models. "
            "Every item keeps its producer, source snapshot, evidence, and decision history."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addLayout(filters)
        layout.addWidget(splitter, 1)
        layout.addLayout(actions)
        layout.addWidget(self._status)
        self._state.currentTextChanged.connect(lambda _text: self.refresh())
        self._assignee.currentTextChanged.connect(lambda _text: self.refresh())
        self._search.returnPressed.connect(self.refresh)

    @Slot()
    def refresh(self) -> None:
        if self._thread is not None:
            return
        self._generation += 1
        generation = self._generation
        self._status.setText("Loading reviewable enrichment…")
        thread = QThread(self)
        worker = _CanonicalReviewWorker(
            generation,
            self._database,
            self._subject_type,
            self._state.currentText(),
            self._search.text().strip(),
            self._assignee.currentText(),
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._loaded)
        worker.failed.connect(self._failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._released)
        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(int, object)
    def _loaded(self, generation: int, rows: object) -> None:
        if generation != self._generation:
            return
        values = rows if isinstance(rows, list) else []
        self._model.replace_rows(values)
        self._status.setText(f"{len(values):,} {self._media_name.casefold()} enrichment record(s) shown.")
        self._accept.setEnabled(False)
        self._reject.setEnabled(False)
        self._assign.setEnabled(False)
        self._unassign.setEnabled(False)

    @Slot(int, str)
    def _failed(self, generation: int, message: str) -> None:
        if generation == self._generation:
            self._model.replace_rows([])
            self._status.setText(f"Review queue unavailable: {message}")

    @Slot()
    def _released(self) -> None:
        self._thread = None
        self._worker = None

    @Slot(QModelIndex)
    def _show_selected(self, index: QModelIndex) -> None:
        row = self._model.row(index.row())
        if row is None:
            return
        def formatted_json(key: str) -> str:
            value = str(row.get(key) or "")
            if not value:
                return "—"
            try:
                return json.dumps(json.loads(value), indent=2, ensure_ascii=False)
            except Exception:
                return value
        fields = (
            ("Subject type", row.get("subject_type")),
            ("Subject", row.get("subject_public_id")),
            ("Enrichment", row.get("enrichment_type")),
            ("Producer", row.get("producer_id")),
            ("Producer version", row.get("producer_version")),
            ("Run", row.get("producer_run_id")),
            ("State", row.get("status")),
            ("Confidence", row.get("confidence")),
            ("Reviewer", row.get("reviewer")),
            ("Assigned to", row.get("assigned_to")),
            ("Assigned by", row.get("assigned_by")),
            ("Assignment note", row.get("assignment_note")),
        )
        table = "".join(
            f"<tr><th align='left'>{name}</th><td>{str(value or '—')}</td></tr>" for name, value in fields
        )
        self._detail.setHtml(
            f"<h3>{str(row.get('summary') or row.get('enrichment_type') or 'Enrichment result')}</h3>"
            f"<table cellspacing='6'>{table}</table>"
            f"<h3>Evidence</h3><pre>{formatted_json('evidence_json')}</pre>"
            f"<h3>Payload</h3><pre>{formatted_json('payload_json')}</pre>"
            f"<h3>Source snapshot</h3><pre>{formatted_json('source_snapshot_json')}</pre>"
        )
        can_review = self._controller is not None and str(row.get("status")) in {
            "generated", "pending_review", "accepted", "rejected"
        }
        self._accept.setEnabled(can_review)
        self._reject.setEnabled(can_review)
        assignable = self._controller is not None and str(row.get("status")) in {
            "generated", "pending_review"
        }
        self._assign.setEnabled(assignable)
        self._unassign.setEnabled(assignable and bool(row.get("assigned_to")))

    def _selected_row(self) -> dict[str, object] | None:
        indexes = self._table.selectionModel().selectedRows()
        return None if not indexes else self._model.row(indexes[0].row())

    def _review(self, action: str) -> None:
        row = self._selected_row()
        if row is None or self._controller is None:
            return
        try:
            from natureai_next.domain.enrichment import SubjectRef, SubjectType

            subject = SubjectRef(SubjectType(str(row["subject_type"])), str(row["subject_public_id"]))
            if action == "accept":
                self._controller.accept(subject, str(row["enrichment_id"]))
            else:
                self._controller.reject(subject, str(row["enrichment_id"]))
            self.refresh()
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, f"{self._media_name} AI Review", str(exc))

    def _assign_selected(self) -> None:
        identity, accepted = QInputDialog.getText(
            self,
            "Defer review to user",
            "User identity ID",
        )
        if not accepted or not identity.strip():
            return
        note, accepted = QInputDialog.getText(
            self,
            "Review assignment",
            "Assignment note (optional)",
        )
        if not accepted:
            return
        self._set_assignment(identity.strip(), note=note)

    def _set_assignment(self, identity: str | None, *, note: str = "") -> None:
        row = self._selected_row()
        if row is None or self._controller is None:
            return
        try:
            from natureai_next.domain.enrichment import SubjectRef, SubjectType

            subject = SubjectRef(SubjectType(str(row["subject_type"])), str(row["subject_public_id"]))
            self._controller.assign_review(
                subject,
                str(row["enrichment_id"]),
                identity,
                note=note,
            )
            self.refresh()
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, f"{self._media_name} AI Review", str(exc))


class _AIReviewOverview(QWidget):
    """Overview for media-specific AI review queues."""

    def __init__(self, photo_review: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._photo_review = photo_review
        layout = QVBoxLayout(self)
        title = QLabel("<h2>AI Review</h2>")
        layout.addWidget(title)
        intro = QLabel(
            "Review model suggestions by media type. Enrichment starts in the relevant Library workspace; "
            "Knowledge Base is the shared place to inspect evidence, provenance, model input, and decisions."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self._photo_status = QLabel()
        self._photo_status.setWordWrap(True)
        self._photo_status.setObjectName("photoAIReviewOverview")
        photo_card = QFrame()
        photo_card.setFrameShape(QFrame.Shape.StyledPanel)
        photo_layout = QVBoxLayout(photo_card)
        photo_layout.addWidget(QLabel("<b>Photos</b>"))
        photo_layout.addWidget(self._photo_status)
        layout.addWidget(photo_card)
        self._media_cards = {"library.photos": photo_card}
        for heading, detail in (
            ("Sounds", "Audio-classification review will show the exact audio segment, waveform, and spectrogram evidence."),
            ("Videos", "Video review will tie suggestions to an exact clip, frame range, or keyframe set."),
            ("Documents", "Document review will retain the exact page or region supplied to the model."),
        ):
            card = QFrame()
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card_layout = QVBoxLayout(card)
            card_layout.addWidget(QLabel(f"<b>{heading}</b>"))
            text = QLabel(detail)
            text.setWordWrap(True)
            card_layout.addWidget(text)
            layout.addWidget(card)
            self._media_cards[f"library.{heading.casefold()}"] = card
        layout.addStretch(1)
        self.refresh()

    def set_library_capability_enabled(self, capability_id: str, enabled: bool) -> None:
        card = self._media_cards.get(capability_id)
        if card is not None:
            card.setVisible(bool(enabled))

    def refresh(self) -> None:
        provider = getattr(self._photo_review, "review_overview", None)
        if not callable(provider):
            self._photo_status.setText(
                "Photo suggestions are reviewed in the Photos tab. The active generation model is shown there."
            )
            return
        try:
            overview = provider()
            counts = dict(getattr(overview, "suggestion_counts", ()))
            model = getattr(overview, "active_model_identity", None) or "No active photo model"
            variant = getattr(overview, "active_variant_identity", None) or ""
            prompt = getattr(overview, "active_prompt_set", None) or "none"
            queue = " · ".join(
                f"{state.title()} {counts.get(state, 0)}"
                for state in ("pending", "accepted", "rejected", "deferred")
            )
            self._photo_status.setText(
                f"<b>Current generation model:</b> {model} {variant}<br>"
                f"<b>Prompt set:</b> {prompt}<br>{queue}"
            )
        except Exception as exc:
            self._photo_status.setText(f"Photo AI review status unavailable: {exc}")


class _PendingMediaReview(QWidget):
    """Honest placeholder for media review capabilities not yet producing suggestions."""

    def __init__(self, media_name: str, evidence: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<h2>{media_name} AI Review</h2>"))
        message = QLabel(
            f"{media_name} enrichment is launched from the {media_name} Library. "
            f"Suggestions will appear here with {evidence} once a compatible capability provider produces reviewable results."
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        layout.addStretch(1)


class MultimodalAIReviewWorkspace(QWidget):
    """Knowledge Base review hub retaining media-specific execution and evidence views."""

    def __init__(
        self,
        photo_review: QWidget,
        *,
        enrichment_database: Path,
        enrichment_controller: object | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._photo_review = photo_review
        self._tabs = QTabWidget()
        self._tabs.setObjectName("multimodalAIReviewTabs")
        self._overview = _AIReviewOverview(photo_review)
        self._canonical_photo_review = CanonicalMediaReview(
            media_name="Photos",
            subject_type="photo",
            database=enrichment_database,
            controller=enrichment_controller,
        )
        self._tabs.addTab(self._overview, "Overview")
        self._tabs.addTab(photo_review, "Photos")
        self._tabs.addTab(self._canonical_photo_review, "Photo Results")
        self._tabs.addTab(
            CanonicalMediaReview(
                media_name="Sounds",
                subject_type="sound",
                database=enrichment_database,
                controller=enrichment_controller,
            ),
            "Sounds",
        )
        self._tabs.addTab(
            CanonicalMediaReview(
                media_name="Videos",
                subject_type="video",
                database=enrichment_database,
                controller=enrichment_controller,
            ),
            "Videos",
        )
        self._tabs.addTab(
            CanonicalMediaReview(
                media_name="Documents",
                subject_type="document",
                database=enrichment_database,
                controller=enrichment_controller,
            ),
            "Documents",
        )
        self._tabs.addTab(
            _PendingMediaReview(
                "Comparisons",
                "side-by-side results after two compatible models have analyzed the same subject",
            ),
            "Comparisons",
        )
        self._tabs.addTab(
            CanonicalMediaReview(
                media_name="Accepted Knowledge",
                subject_type=None,
                database=enrichment_database,
                controller=enrichment_controller,
                initial_state="accepted",
            ),
            "Accepted Knowledge",
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tabs)
        self._media_tabs = {
            "library.photos": photo_review,
            "library.sounds": self._tabs.widget(3),
            "library.videos": self._tabs.widget(4),
            "library.documents": self._tabs.widget(5),
        }
        # Each canonical media review owns a lazy SQLite query. Previously only the
        # tab that happened to be active when Knowledge Base was opened was refreshed
        # (normally Photos). Switching to Sounds, Videos or Documents therefore left
        # an empty, never-loaded model even though enrichment_records existed.
        self._tabs.currentChanged.connect(self._refresh_selected_review)

    @Slot(int)
    def _refresh_selected_review(self, _index: int) -> None:
        current = self._tabs.currentWidget()
        if current is not self._overview and hasattr(current, "refresh"):
            current.refresh()

    def set_library_capability_enabled(self, capability_id: str, enabled: bool) -> None:
        """Hide review functions when their authoritative Library is disabled."""
        widget = self._media_tabs.get(capability_id)
        if widget is None:
            return
        index = self._tabs.indexOf(widget)
        if index >= 0:
            self._tabs.setTabVisible(index, bool(enabled))
        self._overview.set_library_capability_enabled(capability_id, enabled)
        if not enabled and self._tabs.currentWidget() is widget:
            self._tabs.setCurrentWidget(self._overview)

    def refresh(self) -> None:
        self._overview.refresh()
        current = self._tabs.currentWidget()
        if current is not self._overview and hasattr(current, "refresh"):
            current.refresh()

    def show_photos(self) -> None:
        self._tabs.setCurrentIndex(1)
        if hasattr(self._photo_review, "refresh"):
            self._photo_review.refresh()


class KnowledgeBaseWorkspace(QWidget):
    """Top-level, independently persisted workspace for all enrichment knowledge."""

    def __init__(
        self,
        *,
        library_database: Path,
        enrichment_database: Path,
        ai_review: QWidget,
        gbif_taxonomy: QWidget,
        enrichment_controller: object | None = None,
        reference_taxonomy: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("knowledgeBaseWorkspace")
        self._settings = QSettings()
        self._active = False
        self._data = KnowledgeDataView(library_database, self)
        self._tabs = QTabWidget()
        self._tabs.setObjectName("knowledgeBaseTabs")
        self._tabs.addTab(self._data, "All Knowledge")
        self._ai_review_hub = MultimodalAIReviewWorkspace(
            ai_review,
            enrichment_database=enrichment_database,
            enrichment_controller=enrichment_controller,
        )
        self._tabs.addTab(self._ai_review_hub, "AI Review")
        self._tabs.addTab(gbif_taxonomy, "Taxonomy · GBIF")
        if reference_taxonomy is not None:
            self._tabs.addTab(reference_taxonomy, "Reference Knowledge")
        navigation = QWidget()
        navigation.setMinimumWidth(180)
        navigation.setMaximumWidth(280)
        nav_layout = QVBoxLayout(navigation)
        title = QLabel("Knowledge Base")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        nav_layout.addWidget(title)
        intro = QLabel(
            "Search and review AI predictions, independent taxonomy sources, and applied enrichment without crowding the Library inspector."
        )
        intro.setWordWrap(True)
        nav_layout.addWidget(intro)
        for text, index in (
            ("All Knowledge", 0),
            ("AI Review", 1),
            ("Taxonomy · GBIF", 2),
        ):
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, i=index: self._tabs.setCurrentIndex(i))
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("knowledgeBaseMainSplitter")
        self._splitter.addWidget(navigation)
        self._splitter.addWidget(self._tabs)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._splitter)
        saved = self._settings.value("ui/knowledge_base/main_splitter")
        if saved is not None:
            self._splitter.restoreState(saved)
        else:
            self._splitter.setSizes((220, 980))
        self._ai_review = ai_review
        self._gbif = gbif_taxonomy
        self._reference = reference_taxonomy

    def activate(self) -> None:
        self._active = True
        current = self._tabs.currentWidget()
        if current is self._data:
            if not self._data._loaded_once and not self._data._query_active:
                self._data.refresh()
        elif hasattr(current, "refresh"):
            current.refresh()

    def deactivate(self) -> None:
        self._active = False
        self._settings.setValue("ui/knowledge_base/main_splitter", self._splitter.saveState())

    def show_ai_review(self) -> None:
        self._tabs.setCurrentIndex(1)
        self._ai_review_hub.show_photos()

    def set_library_capability_enabled(self, capability_id: str, enabled: bool) -> None:
        self._ai_review_hub.set_library_capability_enabled(capability_id, enabled)

    def show_taxonomy(self) -> None:
        self._tabs.setCurrentIndex(2)
        if hasattr(self._gbif, "refresh"):
            self._gbif.refresh()

    def show_taxon(self, taxon_public_id: str, local_identity: bool = True) -> None:
        if self._reference is not None and hasattr(self._reference, "show_taxon"):
            self._tabs.setCurrentWidget(self._reference)
            self._reference.show_taxon(taxon_public_id, local_identity=local_identity)
        else:
            self.show_taxonomy()

    def refresh(self) -> None:
        self._data.refresh()
        current = self._tabs.currentWidget()
        if current is not self._data and hasattr(current, "refresh"):
            current.refresh()
