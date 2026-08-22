"""PySide6 AI Review workspace built on presentation and application services only."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from natureai_next.application.ai_generation import (
    LocalSuggestionGenerationService,
    SuggestionGenerationResult,
)
from natureai_next.application.ai_resources import LocalAIResourceService
from natureai_next.application.ai_review import ReviewFilter, SuggestionService
from natureai_next.application.components import ResourceComponentRegistry
from natureai_next.application.knowledge_engine import KnowledgeEngine
from natureai_next.application.observation_intelligence import ObservationIntelligenceService
from natureai_next.domain.ai import SuggestionDetail, SuggestionProjection
from natureai_next.ui.presentation.ai_review import AIReviewModel

try:
    from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
    from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QInputDialog,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSizePolicy,
        QSplitter,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


class _GenerationWorker(QObject):
    progress = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self, service: LocalSuggestionGenerationService, asset_ids: tuple[str, ...]
    ) -> None:
        super().__init__()
        self._service = service
        self._asset_ids = asset_ids
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.generate_selected(
                self._asset_ids,
                cancellation_check=self._check_cancelled,
                progress=lambda current, total, message: self.progress.emit(
                    current, total, message
                ),
            )
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()

    def cancel(self) -> None:
        self._cancelled = True

    def _check_cancelled(self) -> None:
        if self._cancelled:
            raise RuntimeError("BioCLIP generation was cancelled.")


class AIReviewWorkspace(QWidget):
    resources_requested = Signal()
    observation_requested = Signal(str)
    """Keyboard-first review surface with no database or filesystem dependencies."""

    def __init__(
        self,
        *,
        model: AIReviewModel,
        service: SuggestionService,
        action_id_factory: Callable[[], str],
        now_us: Callable[[], int],
        generation_service: LocalSuggestionGenerationService | None = None,
        selected_asset_ids: Callable[[], tuple[str, ...]] = lambda: (),
        resource_service: LocalAIResourceService | None = None,
        regional_service: object | None = None,
        regional_acquisition_service: object | None = None,
        observation_service: ObservationIntelligenceService | None = None,
        knowledge_engine: KnowledgeEngine | None = None,
        ecology_service: object | None = None,
        thumbnail_service: object | None = None,
        component_registry: ResourceComponentRegistry | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model = model
        self._service = service
        self._action_id_factory = action_id_factory
        self._now_us = now_us
        self._generation_service = generation_service
        self._selected_asset_ids = selected_asset_ids
        self._resource_service = resource_service
        self._regional_service = regional_service
        self._regional_acquisition_service = regional_acquisition_service
        self._observation_service = observation_service
        self._knowledge_engine = knowledge_engine
        self._ecology_service = ecology_service
        self._thumbnail_service = thumbnail_service
        self._components = component_registry or ResourceComponentRegistry()
        if regional_acquisition_service is not None:
            from natureai_next.ui.qt.activity import activity_center

            activity_center().register_recovery(
                "regional-knowledge", regional_acquisition_service.recovery_operation
            )
        self._generation_thread: QThread | None = None
        self._generation_worker: _GenerationWorker | None = None
        self._items_by_id: dict[str, SuggestionProjection] = {}
        self._current_asset_public_id: str | None = None

        self.setObjectName("photoAIReviewWorkspace")
        self._model_status = QLabel()
        self._model_status.setObjectName("photoReviewModelStatus")
        self._model_status.setWordWrap(True)
        self._queue_status = QLabel()
        self._queue_status.setObjectName("photoReviewQueueStatus")
        self._queue_status.setWordWrap(True)

        self._state_filter = QComboBox()
        self._state_filter.addItems(["pending", "deferred", "accepted", "rejected", "superseded"])
        self._state_filter.currentTextChanged.connect(self.refresh)
        self._confidence_filter = QComboBox()
        self._confidence_filter.addItems(
            ["all", "high", "medium", "low", "unknown", "unclassified"]
        )
        self._confidence_filter.currentTextChanged.connect(self.refresh)
        self._current_photo_only = QCheckBox("Current photograph only")
        self._current_photo_only.setToolTip(
            "Show only taxonomy suggestions for the selected photograph."
        )
        self._current_photo_only.toggled.connect(self._photo_filter_toggled)
        self._assignee_filter = QComboBox()
        self._assignee_filter.setEditable(True)
        self._assignee_filter.addItems(("All assignees", "Unassigned"))
        self._assignee_filter.setToolTip(
            "Choose or type a user identity ID to view that person's assigned queue."
        )
        self._assignee_filter.currentTextChanged.connect(self.refresh)

        self._list = QListWidget()
        self._list.setObjectName("photoSuggestionQueue")
        self._list.setAlternatingRowColors(True)
        self._list.setMinimumWidth(245)
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.setToolTip("Select one or more suggestions. Ctrl/Shift-click selects multiple rows for bulk review.")
        self._list.currentItemChanged.connect(self._selection_changed)

        self._detail = QTextBrowser()
        self._detail.setObjectName("photoSuggestionDetails")
        self._detail.setOpenExternalLinks(False)
        self._preview = QLabel("Select a suggestion to preview its photograph")
        self._preview.setObjectName("photoSourcePreview")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(440, 300)
        self._preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._preview.setStyleSheet(
            "QLabel { background: #151817; color: #c8c8c8; border: 1px solid #465047; }"
        )
        self._preview_meta = QLabel()
        self._preview_meta.setObjectName("photoSourceMetadata")
        self._preview_meta.setWordWrap(True)
        self._inference_preview = QLabel("Model-input image will appear here")
        self._inference_preview.setObjectName("photoModelInputPreview")
        self._inference_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._inference_preview.setMinimumHeight(230)
        self._inference_preview.setStyleSheet(
            "QLabel { background: #151817; color: #c8c8c8; border: 1px solid #465047; }"
        )
        self._inference_meta = QLabel(
            "The exact persisted crop supplied to BioCLIP is shown for new inference runs."
        )
        self._inference_meta.setWordWrap(True)
        self._candidate_heading = QLabel("Select a suggestion")
        self._candidate_heading.setObjectName("photoCandidateHeading")
        self._candidate_heading.setStyleSheet("font-size: 17px; font-weight: 600;")
        self._candidate_score = QLabel()
        self._candidate_score.setObjectName("photoCandidateScore")
        self._candidate_score.setStyleSheet("font-size: 22px; font-weight: 600;")
        self._status = QLabel("Ready")
        self._shortcut_hint = QLabel(
            "J/K navigate • A accept • Shift+Enter accept all pending & next • R reject • D defer • F1 help"
        )
        self._shortcut_hint.setAccessibleName("AI Review keyboard shortcuts")
        self._shortcut_hint.setWordWrap(True)

        accept = QPushButton("Accept selected")
        accept.setObjectName("photoReviewAccept")
        accept_next = QPushButton("Accept & Next")
        accept_next.setObjectName("photoReviewAcceptNext")
        accept_resolve = QPushButton("Accept one; reject remaining")
        reject_others = QPushButton("Reject remaining unconfirmed")
        reject_all = QPushButton("Reject all unconfirmed")
        reject = QPushButton("Reject selected")
        reject.setObjectName("photoReviewReject")
        defer = QPushButton("Defer selected")
        defer.setObjectName("photoReviewDefer")
        defer_user = QPushButton("Defer to user…")
        defer_user.setObjectName("photoReviewAssign")
        return_queue = QPushButton("Return to shared queue")
        reverse = QPushButton("Reverse acceptance")
        refresh = QPushButton("Refresh")
        more = QPushButton("Load more")
        self._generate = QPushButton("Generate selected")
        self._resources = QPushButton("AI Resources")
        self._observation_history = QPushButton("Observation History")
        self._cancel_generation = QPushButton("Cancel generation")
        self._cancel_generation.setEnabled(False)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        accept.clicked.connect(lambda: self._apply_selected("accept"))
        accept_next.clicked.connect(self._accept_all_pending_and_next)
        accept_resolve.clicked.connect(self._accept_and_reject_rest)
        reject_others.clicked.connect(self._reject_other_options)
        reject_all.clicked.connect(self._reject_all_unconfirmed)
        reject.clicked.connect(lambda: self._apply_selected("reject"))
        defer.clicked.connect(lambda: self._apply_selected("defer"))
        defer_user.clicked.connect(self._assign_selected)
        return_queue.clicked.connect(lambda: self._set_assignment(None))
        reverse.clicked.connect(lambda: self._apply("reverse"))
        refresh.clicked.connect(self.refresh)
        more.clicked.connect(self.load_more)
        self._generate.clicked.connect(self.generate_selected)
        self._resources.clicked.connect(self.resources_requested.emit)
        self._observation_history.clicked.connect(self._open_observation_history)
        self._cancel_generation.clicked.connect(self.cancel_generation)
        self._generate.setEnabled(self._generation_service is not None)
        self._resources.setEnabled(self._resource_service is not None)

        filters_panel = QGroupBox("Filters")
        filters_panel.setObjectName("photoReviewFilters")
        filters_panel.setMinimumWidth(150)
        filters_panel.setMaximumWidth(220)
        filters_layout = QVBoxLayout(filters_panel)
        filters_layout.addWidget(QLabel("State"))
        filters_layout.addWidget(self._state_filter)
        filters_layout.addWidget(QLabel("Confidence"))
        filters_layout.addWidget(self._confidence_filter)
        filters_layout.addWidget(self._current_photo_only)
        filters_layout.addWidget(QLabel("Assigned review queue"))
        filters_layout.addWidget(self._assignee_filter)
        filters_layout.addSpacing(8)
        filters_layout.addWidget(refresh)
        filters_layout.addStretch(1)

        suggestions_panel = QGroupBox("Suggestions")
        suggestions_panel.setObjectName("photoReviewSuggestions")
        suggestions_layout = QVBoxLayout(suggestions_panel)
        suggestions_layout.addWidget(self._list, 1)
        suggestions_layout.addWidget(more)

        source_group = QGroupBox("Source photograph")
        source_layout = QVBoxLayout(source_group)
        source_layout.addWidget(self._preview, 1)
        source_layout.addWidget(self._preview_meta)

        input_group = QGroupBox("Image used for this rating (model input)")
        input_group.setObjectName("photoReviewModelInputCard")
        input_layout = QVBoxLayout(input_group)
        input_layout.addWidget(self._inference_meta)
        input_layout.addWidget(self._inference_preview, 1)

        evidence_panel = QWidget()
        evidence_layout = QVBoxLayout(evidence_panel)
        evidence_layout.setContentsMargins(0, 0, 0, 0)
        evidence_layout.addWidget(source_group, 3)
        evidence_layout.addWidget(input_group, 2)

        decision_group = QGroupBox("AI suggestion")
        decision_group.setObjectName("photoReviewDecisionPanel")
        decision_layout = QVBoxLayout(decision_group)
        decision_layout.addWidget(self._candidate_heading)
        decision_layout.addWidget(self._candidate_score)
        decision_layout.addWidget(self._detail, 1)

        review_splitter = QSplitter(Qt.Orientation.Horizontal)
        review_splitter.setObjectName("photoReviewMainSplitter")
        review_splitter.addWidget(filters_panel)
        review_splitter.addWidget(suggestions_panel)
        review_splitter.addWidget(evidence_panel)
        review_splitter.addWidget(decision_group)
        review_splitter.setStretchFactor(0, 0)
        review_splitter.setStretchFactor(1, 1)
        review_splitter.setStretchFactor(2, 4)
        review_splitter.setStretchFactor(3, 2)
        review_splitter.setSizes((170, 270, 670, 360))

        actions = QHBoxLayout()
        actions.addStretch(1)
        for button in (
            accept,
            accept_next,
            reject,
            defer,
            defer_user,
            return_queue,
            accept_resolve,
            reject_others,
            reject_all,
            reverse,
            self._observation_history,
            self._resources,
            self._generate,
            self._cancel_generation,
        ):
            actions.addWidget(button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        header = QHBoxLayout()
        header.addWidget(self._model_status, 2)
        header.addWidget(self._queue_status, 1)
        layout.addLayout(header)
        layout.addWidget(review_splitter, 1)
        layout.addLayout(actions)
        layout.addWidget(self._progress)
        layout.addWidget(self._status)
        layout.addWidget(self._shortcut_hint)

        accept.setToolTip("Accept all selected suggestions (A)")
        accept_next.setToolTip(
            "Accept all pending suggestions for this photograph and move to the next pending photograph (Shift+Enter)"
        )
        reject.setToolTip("Reject all selected suggestions (R)")
        defer.setToolTip("Defer all selected suggestions (D)")
        reverse.setToolTip("Reverse acceptance (Ctrl+Z)")

        QShortcut(QKeySequence("A"), self, activated=lambda: self._apply_selected("accept"))
        QShortcut(QKeySequence("Shift+Return"), self, activated=self._accept_all_pending_and_next)
        QShortcut(QKeySequence("O"), self, activated=self._open_observation_history)
        QShortcut(QKeySequence("R"), self, activated=lambda: self._apply_selected("reject"))
        QShortcut(QKeySequence("D"), self, activated=lambda: self._apply_selected("defer"))
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=lambda: self._apply("reverse"))
        QShortcut(QKeySequence(Qt.Key.Key_J), self, activated=self._select_next)
        QShortcut(QKeySequence(Qt.Key.Key_K), self, activated=self._select_previous)
        self.refresh()

    @property
    def observation_service(self) -> ObservationIntelligenceService | None:
        return self._observation_service

    @property
    def knowledge_engine(self) -> KnowledgeEngine | None:
        return self._knowledge_engine

    @property
    def thumbnail_service(self) -> object | None:
        return self._thumbnail_service

    @property
    def ecology_service(self) -> object | None:
        return self._ecology_service

    @property
    def resource_service(self) -> LocalAIResourceService | None:
        return self._resource_service

    @property
    def regional_service(self) -> object | None:
        return self._regional_service

    @property
    def regional_acquisition_service(self) -> object | None:
        return self._regional_acquisition_service

    @property
    def suggestion_service(self) -> SuggestionService:
        return self._service

    @property
    def generation_busy(self) -> bool:
        return self._generation_thread is not None and self._generation_thread.isRunning()

    def set_workspace_enabled(self, enabled: bool) -> None:
        """Keep BioCLIP analysis lifecycle aligned with the Photos workspace."""
        self.setEnabled(enabled)
        if not enabled and self.generation_busy:
            self.cancel_generation()
            self._status.setText(
                "Photos workspace disabled; cancelling active BioCLIP analysis…"
            )

    @Slot()
    def generate_selected(self) -> None:
        if not self._components.enabled("bioclip"):
            QMessageBox.information(
                self,
                "BioCLIP disabled",
                "Enable BioCLIP / OpenCLIP under Settings → Resource Components first.",
            )
            return
        if self._generation_service is None or self.generation_busy:
            return
        asset_ids = self._selected_asset_ids()
        if not asset_ids:
            QMessageBox.information(
                self,
                "BioCLIP suggestions",
                "Select one or more photographs in the Library, then return to AI Review.",
            )
            return
        thread = QThread(self)
        worker = _GenerationWorker(self._generation_service, asset_ids)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._generation_progress)
        worker.succeeded.connect(self._generation_succeeded)
        worker.failed.connect(self._generation_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._generation_finished)
        self._generation_thread = thread
        self._generation_worker = worker
        self._generate.setEnabled(False)
        self._cancel_generation.setEnabled(True)
        self._progress.setVisible(True)
        self._progress.setRange(0, max(1, len(asset_ids)))
        self._progress.setValue(0)
        self._status.setText(f"Starting local BioCLIP inference for {len(asset_ids)} asset(s)…")
        thread.start()

    @Slot()
    def cancel_generation(self) -> None:
        if self._generation_worker is not None:
            self._generation_worker.cancel()
            self._status.setText("Cancellation requested…")
            self._cancel_generation.setEnabled(False)

    @Slot(int, int, str)
    def _generation_progress(self, current: int, total: int, message: str) -> None:
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(current)
        self._status.setText(message)

    @Slot(object)
    def _generation_succeeded(self, result: object) -> None:
        if not isinstance(result, SuggestionGenerationResult):
            self._status.setText("BioCLIP generation returned an invalid result.")
            return
        self._status.setText(
            f"BioCLIP complete: {result.completed_assets}/{result.requested} assets, "
            f"{result.suggestions_created} suggestions, {len(result.failed)} failures."
        )
        self.refresh()

    @Slot(str)
    def _generation_failed(self, message: str) -> None:
        self._status.setText(message)
        QMessageBox.warning(self, "BioCLIP generation failed", message)
        self.refresh()

    @Slot()
    def _generation_finished(self) -> None:
        self._generation_thread = None
        self._generation_worker = None
        self._generate.setEnabled(
            self._components.enabled("bioclip") and self._generation_service is not None
        )
        self._cancel_generation.setEnabled(False)
        self._progress.setVisible(False)

    def review_overview(self):
        """Return the current photo-review overview for the multimodal Knowledge Base."""
        return self._service.overview()

    def refresh(self, *_args: object) -> None:
        enabled = self._components.enabled("bioclip")
        self._generate.setEnabled(
            enabled and self._generation_service is not None and not self.generation_busy
        )
        if not enabled:
            self._model_status.setText(
                "<b>BioCLIP / OpenCLIP:</b> disabled under Settings → Resource Components. Installed models and prior results remain available."
            )
        try:
            overview = self._service.overview()
            if not enabled:
                pass
            elif overview.active_model_identity is None:
                self._model_status.setText(
                    "<b>BioCLIP model:</b> no active model package. "
                    "Install and activate a local model package before generating suggestions."
                )
            else:
                self._model_status.setText(
                    "<b>Reviewing legacy BioCLIP suggestions</b> · <b>Current generation model (legacy suggestion engine):</b> "
                    f"{escape(overview.active_model_identity)} {escape(overview.active_model_version or '')} "
                    f"· {escape(overview.active_variant_identity or '')} "
                    f"· prompt set: {escape(overview.active_prompt_set or 'none')}"
                )
            counts = dict(overview.suggestion_counts)
            self._queue_status.setText(
                "<b>Review queues:</b> "
                + " · ".join(
                    f"{state} {counts.get(state, 0)}"
                    for state in ("pending", "deferred", "accepted", "rejected", "superseded")
                )
                + (
                    ""
                    if overview.latest_run_outcome is None
                    else f" · latest inference: {escape(overview.latest_run_outcome)} "
                    f"({overview.latest_run_completed} completed, {overview.latest_run_failed} failed)"
                )
            )
        except Exception as exc:
            self._model_status.setText(f"<b>AI status unavailable:</b> {escape(str(exc))}")
            self._queue_status.clear()

        confidence = self._confidence_filter.currentText()
        filter_value = ReviewFilter(
            state=self._state_filter.currentText(),
            confidence=() if confidence == "all" else (confidence,),
            assigned_to=(
                None
                if self._assignee_filter.currentText() == "All assignees"
                else (
                    ""
                    if self._assignee_filter.currentText() == "Unassigned"
                    else self._assignee_filter.currentText().strip()
                )
            ),
        )
        if self._current_photo_only.isChecked() and self._current_asset_public_id:
            state = self._model.refresh_asset(self._current_asset_public_id, filter_value)
        else:
            state = self._model.refresh(filter_value)
        self._render(state.items, replace=True)
        if state.error:
            self._status.setText(state.error)
        elif state.items:
            self._status.setText(f"{len(state.items)} suggestions shown")
        else:
            self._status.setText(
                f"No {self._state_filter.currentText()} suggestions match the current filter."
            )
            self._detail.setHtml(
                "<h3>No photo suggestions</h3>"
                "<p>Photo-model evidence is stored separately from confirmed catalog taxonomy. "
                "Suggestions will appear here after a local inference run has completed.</p>"
            )

    def load_more(self) -> None:
        before = len(self._model.state.items)
        state = self._model.load_more()
        self._render(state.items[before:], replace=False)
        self._status.setText(state.error or f"{len(state.items)} suggestions shown")

    def _render(self, items: tuple[SuggestionProjection, ...], *, replace: bool) -> None:
        selected = self._selected_id()
        if replace:
            self._list.clear()
            self._items_by_id.clear()
        for projection in items:
            self._items_by_id[projection.public_id] = projection
            label = projection.candidate_label or "Unknown"
            score = projection.calibrated_score
            score_text = "—" if score is None else f"{score:.3f}"
            item = QListWidgetItem(
                f"#{projection.rank}  {label}  ·  {score_text}  ·  "
                f"{projection.confidence_band.value}"
                + (f"  ·  assigned: {projection.assigned_to}" if projection.assigned_to else "")
            )
            item.setData(Qt.ItemDataRole.UserRole, projection.public_id)
            item.setToolTip(f"Asset {projection.asset_public_id}")
            self._list.addItem(item)
            if projection.public_id == selected:
                self._list.setCurrentItem(item)
        if self._list.currentRow() < 0 and self._list.count():
            self._list.setCurrentRow(0)

    def _selection_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        public_id = str(current.data(Qt.ItemDataRole.UserRole))
        projection = self._items_by_id.get(public_id)
        if projection is not None:
            self._current_asset_public_id = projection.asset_public_id
        self._model.select(public_id)
        try:
            region_code = (
                None
                if self._regional_service is None
                else self._regional_service.primary_region_code()
            )
            detail = self._service.detail(public_id, region_code=region_code)
            evidence = (
                None
                if self._regional_service is None
                else self._regional_service.evidence_for_taxon(
                    detail.suggestion.candidate_taxon_public_id
                )
            )
            personal = (
                self._knowledge_engine.observation_context(
                    detail.suggestion.candidate_taxon_public_id
                )
                if self._knowledge_engine is not None
                else (
                    None
                    if self._observation_service is None
                    else self._observation_service.context_for_taxon(
                        detail.suggestion.candidate_taxon_public_id
                    )
                )
            )
            ecology = (
                None
                if self._ecology_service is None
                else self._ecology_service.for_taxon(detail.suggestion.candidate_taxon_public_id)
            )
            self._load_preview(detail)
            self._load_inference_preview(detail)
            candidate = detail.taxon_scientific_name or detail.suggestion.candidate_label or "Unknown"
            score = (
                detail.suggestion.calibrated_score
                if detail.suggestion.calibrated_score is not None
                else detail.suggestion.raw_score
            )
            self._candidate_heading.setText(candidate)
            self._candidate_score.setText(
                f"{score:.4f} · {detail.suggestion.confidence_band.value.title()} confidence"
            )
            enrichment = (
                None
                if self._knowledge_engine is None
                else self._knowledge_engine.asset_enrichment(detail.suggestion.asset_public_id)
            )
            self._detail.setHtml(
                self._detail_html(detail, evidence, personal, ecology)
                + self._enrichment_html(enrichment)
            )
        except Exception as exc:
            self._detail.setPlainText(str(exc))

    def _load_preview(self, detail: SuggestionDetail) -> None:
        self._preview.clear()
        self._preview.setText("Loading photograph…")
        path = Path(detail.asset_primary_path) if detail.asset_primary_path else None
        cached = Path(detail.asset_thumbnail_path) if detail.asset_thumbnail_path else None
        data = None
        try:
            if self._thumbnail_service is not None:
                data = self._thumbnail_service.load(
                    source_path=path, cached_path=cached, max_size=1200
                )
        except Exception:
            data = None
        pixmap = QPixmap()
        if data and pixmap.loadFromData(data):
            scaled = pixmap.scaled(
                self._preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._preview.setPixmap(scaled)
        else:
            self._preview.setText("Preview unavailable")
        filename = "—" if path is None else path.name
        captured = detail.asset_capture_local_text or ""
        if not captured and detail.asset_capture_time_utc_us is not None:
            captured = datetime.fromtimestamp(
                detail.asset_capture_time_utc_us / 1_000_000, tz=UTC
            ).strftime("%Y-%m-%d %H:%M:%S UTC")
        self._preview_meta.setText(
            f"{filename}" + (f"  ·  Captured {captured}" if captured else "")
        )

    def _load_inference_preview(self, detail: SuggestionDetail) -> None:
        self._inference_preview.clear()
        path = Path(detail.inference_image_path) if detail.inference_image_path else None
        if path is None or not path.is_file():
            self._inference_preview.setText(
                "Model-input snapshot unavailable for this inference. Regenerate to retain it."
            )
            self._inference_meta.setText(
                "Older results remain valid, but their exact model-input image was not retained."
            )
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._inference_preview.setText("Persisted model-input snapshot could not be decoded")
            self._inference_meta.setText(str(path))
            return
        scaled = pixmap.scaled(
            self._inference_preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._inference_preview.setPixmap(scaled)
        dimensions = (
            f"{detail.inference_image_width} × {detail.inference_image_height}"
            if detail.inference_image_width and detail.inference_image_height
            else f"{pixmap.width()} × {pixmap.height()}"
        )
        self._inference_meta.setText(
            f"Exact persisted BioCLIP input · {dimensions} · {path.suffix.lstrip('.').upper()}"
        )

    @staticmethod
    def _enrichment_html(dossier: object | None) -> str:
        if dossier is None:
            return ""
        analyses = tuple(getattr(dossier, "analyses", ()))
        candidates = tuple(getattr(dossier, "candidates", ()))
        engines = tuple(getattr(dossier, "engine_ids", ()))
        latest = getattr(dossier, "latest_completed_at_us", None)
        latest_text = AIReviewWorkspace._format_observation_time(latest)
        engine_text = ", ".join(engines) or "—"
        return (
            "<h3>Photo enrichment history</h3>"
            f"<p><b>{len(analyses)}</b> analysis run(s) · <b>{len(candidates)}</b> normalized candidate(s)<br>"
            f"Engines: {escape(engine_text)}<br>Latest completed: {escape(latest_text)}</p>"
        )

    @staticmethod
    def _format_observation_time(value: int | None) -> str:
        if value is None:
            return "—"
        return datetime.fromtimestamp(value / 1_000_000, tz=UTC).strftime("%Y-%m-%d")

    @staticmethod
    def _inference_image_html(detail: SuggestionDetail) -> str:
        if detail.inference_image_path:
            return (
                "<h3>Model-input evidence</h3>"
                "<p>The exact persisted BioCLIP input is displayed in the model-input card beside this panel.</p>"
            )
        return (
            "<h3>Model-input evidence</h3>"
            "<p>The exact model-input snapshot was not retained for this older inference. "
            "Generate the suggestion again to create it.</p>"
        )

    @staticmethod
    def _why_html(
        detail: SuggestionDetail,
        evidence: object | None,
        personal: object | None,
        ecology: object | None,
    ) -> str:
        suggestion = detail.suggestion
        points: list[str] = []
        score = (
            suggestion.calibrated_score
            if suggestion.calibrated_score is not None
            else suggestion.raw_score
        )
        points.append(
            f"The local visual model ranked this candidate #{suggestion.rank} with a score of {score:.3f} ({suggestion.confidence_band.value})."
        )
        if evidence is not None and getattr(evidence, "label", None):
            points.append(f"Regional occurrence evidence: {evidence.label}.")
        if ecology is not None:
            months = set(getattr(ecology, "seasonal_months", ()))
            capture_us = detail.asset_capture_time_utc_us
            if capture_us is not None and months:
                month = datetime.fromtimestamp(capture_us / 1_000_000, tz=UTC).month
                points.append(
                    f"The photograph was captured in month {month}; this month is {'inside' if month in months else 'outside'} the installed seasonal range."
                )
            habitats = tuple(getattr(ecology, "habitats", ()))
            if habitats:
                points.append(
                    "Known habitats in the installed context include " + ", ".join(habitats) + "."
                )
            status = getattr(ecology, "conservation_status", None)
            if status:
                points.append(
                    f"Installed conservation context: {status}. This is informational and does not change identification confidence."
                )
        if personal is not None:
            count = int(getattr(personal, "confirmed_observations", 0))
            points.append(
                "This would be your first confirmed observation."
                if count == 0
                else f"You previously confirmed this taxon {count} time(s)."
            )
        items = "".join(f"<li>{escape(point)}</li>" for point in points)
        return (
            AIReviewWorkspace._inference_image_html(detail)
            + "<h3>Why this suggestion?</h3><ul>" + items + "</ul>"
            "<p><i>Feature-level visual explanations (for example plumage, bill shape, or leaf structure) are not available from the installed BioCLIP package, so NatureAI does not invent them.</i></p>"
        )

    @staticmethod
    def _detail_html(
        detail: SuggestionDetail,
        evidence: object | None = None,
        personal: object | None = None,
        ecology: object | None = None,
    ) -> str:
        suggestion = detail.suggestion
        fields = (
            ("Asset", suggestion.asset_public_id),
            ("Title", detail.asset_title or ""),
            ("Candidate", detail.taxon_scientific_name or suggestion.candidate_label or "Unknown"),
            ("Rank", detail.taxon_rank or suggestion.taxonomic_level or ""),
            ("Confidence", suggestion.confidence_band.value),
            ("Raw score", f"{suggestion.raw_score:.6f}"),
            (
                "Calibrated score",
                "" if suggestion.calibrated_score is None else f"{suggestion.calibrated_score:.6f}",
            ),
            ("Occurrence", detail.regional_occurrence_status or ""),
            ("Regional evidence", "" if evidence is None else getattr(evidence, "label", "")),
            (
                "Occurrence source",
                "" if evidence is None else (getattr(evidence, "source", None) or ""),
            ),
            ("Model", detail.model_variant_public_id),
            ("Preprocessing", detail.preprocessing_identity),
            ("Provider", detail.execution_provider),
            ("Precision", detail.precision or ""),
            (
                "Prompt set",
                " / ".join(filter(None, (detail.prompt_set_identity, detail.prompt_set_version))),
            ),
            ("Inference run", detail.inference_run_public_id),
        )
        rows = "".join(
            f"<tr><th align='left'>{escape(name)}</th><td>{escape(str(value))}</td></tr>"
            for name, value in fields
        )
        personal_html = ""
        if personal is not None:
            count = int(getattr(personal, "confirmed_observations", 0))
            photos = int(getattr(personal, "evidence_photos", 0))
            countries = ", ".join(getattr(personal, "country_codes", ())) or "—"
            if count == 0:
                summary = "This would be your first confirmed observation."
            else:
                summary = (
                    f"Previously confirmed {count} time(s), supported by {photos} photograph(s)."
                )
            first_date = AIReviewWorkspace._format_observation_time(
                getattr(personal, "first_observed_at_us", None)
            )
            last_date = AIReviewWorkspace._format_observation_time(
                getattr(personal, "last_observed_at_us", None)
            )
            personal_html = (
                "<h3>Personal observation context</h3>"
                f"<p><b>{escape(summary)}</b></p>"
                f"<p>First observed: {escape(first_date)}<br>Last observed: {escape(last_date)}<br>Countries: {escape(countries)}</p>"
            )
        ecology_html = ""
        if ecology is not None:
            months = ", ".join(str(x) for x in getattr(ecology, "seasonal_months", ())) or "—"
            habitats = ", ".join(getattr(ecology, "habitats", ())) or "—"
            source = " / ".join(
                filter(
                    None,
                    (
                        getattr(ecology, "source_name", None),
                        getattr(ecology, "source_version", None),
                    ),
                )
            )
            ecology_html = (
                "<h3>Conservation & ecological context</h3>"
                f"<p>Conservation status: <b>{escape(getattr(ecology, 'conservation_status', None) or '—')}</b><br>"
                f"Seasonal months: {escape(months)}<br>Migration: {escape(getattr(ecology, 'migration_status', None) or '—')}<br>"
                f"Habitats: {escape(habitats)}<br>Source: {escape(source or '—')}</p>"
            )
        why_html = AIReviewWorkspace._why_html(detail, evidence, personal, ecology)
        return (
            f"<table cellspacing='6'>{rows}</table>"
            + why_html
            + personal_html
            + ecology_html
            + "<h3>Evidence provenance</h3>"
            f"<pre>{escape(suggestion.provenance_json)}</pre>"
            "<p><b>Accepting a suggestion creates human-confirmed taxonomy metadata. "
            "Rejecting or deferring it changes only the AI review state.</b></p>"
        )

    @Slot(bool)
    def _photo_filter_toggled(self, checked: bool) -> None:
        if checked and self._current_asset_public_id is None:
            selected = self._selected_id()
            projection = None if selected is None else self._items_by_id.get(selected)
            if projection is not None:
                self._current_asset_public_id = projection.asset_public_id
        self.refresh()

    @Slot()
    def _accept_all_pending_and_next(self) -> None:
        public_id = self._selected_id()
        if public_id is None:
            return
        projection = self._items_by_id.get(public_id)
        if projection is None:
            return
        completed_asset = projection.asset_public_id
        try:
            result = self._service.accept_all_pending_for_asset(
                public_id,
                action_id_factory=self._action_id_factory,
                now_us=self._now_us(),
            )
            self._advance_to_next_pending_photo(completed_asset)
            self._status.setText(
                f"Accepted {len(result.reviewed)} pending suggestion(s); opened the next photograph."
                if self._current_asset_public_id is not None
                else f"Accepted {len(result.reviewed)} pending suggestion(s); no pending photograph remains."
            )
        except Exception as exc:
            QMessageBox.critical(self, "AI Review", str(exc))

    @Slot()
    def _accept_and_reject_rest(self) -> None:
        public_id = self._selected_id()
        if public_id is None:
            return
        projection = self._items_by_id.get(public_id)
        if projection is None:
            return
        try:
            was_first = False
            if self._observation_service is not None:
                context = self._observation_service.context_for_taxon(
                    projection.candidate_taxon_public_id
                )
                was_first = bool(context is not None and context.is_first_observation)
            result = self._service.accept_and_reject_others(
                public_id,
                action_id_factory=self._action_id_factory,
                now_us=self._now_us(),
            )
            rejected = max(0, len(result.reviewed) - 1)
            self._advance_to_next_pending_photo(projection.asset_public_id)
            message = (
                f"Accepted the selected suggestion and rejected {rejected} other pending option(s)."
            )
            if was_first:
                message += " This is your first confirmed observation of this taxon."
            if self._current_asset_public_id is not None:
                message += " Opened the next photograph."
            else:
                message += " No pending photograph remains."
            self._status.setText(message)
        except Exception as exc:
            QMessageBox.critical(self, "AI Review", str(exc))

    @Slot()
    def _reject_other_options(self) -> None:
        public_id = self._selected_id()
        if public_id is None:
            return
        try:
            result = self._service.reject_other_suggestions(
                public_id,
                action_id_factory=self._action_id_factory,
                now_us=self._now_us(),
            )
            QMessageBox.information(
                self,
                "Other taxonomy options rejected",
                f"Rejected {len(result.reviewed)} remaining option(s) for this photograph.",
            )
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "AI Review", str(exc))

    @Slot()
    def _reject_all_unconfirmed(self) -> None:
        public_id = self._selected_id()
        projection = None if public_id is None else self._items_by_id.get(public_id)
        if projection is None:
            return
        try:
            result = self._service.reject_all_pending_for_asset(
                projection.asset_public_id,
                action_id_factory=self._action_id_factory,
                now_us=self._now_us(),
            )
            self._status.setText(
                f"Rejected {len(result.reviewed)} unconfirmed suggestion(s) for this observation."
            )
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "AI Review", str(exc))

    @Slot()
    def _open_observation_history(self) -> None:
        public_id = self._selected_id()
        projection = None if public_id is None else self._items_by_id.get(public_id)
        if projection is not None and projection.candidate_taxon_public_id:
            self.observation_requested.emit(projection.candidate_taxon_public_id)

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
        if accepted:
            self._set_assignment(identity.strip(), note)

    def _set_assignment(self, identity: str | None, note: str = "") -> None:
        selected = self._selected_id()
        if selected is None:
            return
        try:
            self._service.assign(
                selected,
                assigned_to=identity,
                assigned_by="local-user",
                now_us=self._now_us(),
                note=note,
            )
            self._status.setText(
                "Review returned to the shared queue."
                if identity is None
                else f"Review deferred to {identity}."
            )
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Review assignment", str(exc))

    def _selected_ids(self) -> tuple[str, ...]:
        values = []
        for item in self._list.selectedItems():
            value = str(item.data(Qt.ItemDataRole.UserRole))
            if value and value not in values:
                values.append(value)
        if values:
            return tuple(values)
        current = self._selected_id()
        return () if current is None else (current,)

    def _apply_selected(self, action: str) -> None:
        selected = self._selected_ids()
        if not selected:
            return
        if len(selected) == 1:
            self._apply(action)
            return
        try:
            result = self._service.batch_review(
                selected,
                action=action,
                action_id_factory=self._action_id_factory,
                now_us=self._now_us(),
            )
            self.refresh()
            message = f"{len(result.reviewed)} selected suggestion(s) {action}ed."
            if result.failed:
                message += f" {len(result.failed)} failed."
            self._status.setText(message)
            if result.failed:
                QMessageBox.warning(
                    self,
                    "Bulk review partly completed",
                    message + "\n\n" + "\n".join(f"{item}: {reason}" for item, reason in result.failed),
                )
        except Exception as exc:
            QMessageBox.critical(self, "AI Review", str(exc))

    def _apply(self, action: str) -> None:
        public_id = self._selected_id()
        if public_id is None:
            return
        try:
            kwargs = {"action_public_id": self._action_id_factory(), "now_us": self._now_us()}
            if action == "accept":
                was_first = False
                projection = self._items_by_id.get(public_id)
                before = None
                if projection is not None and self._observation_service is not None:
                    before = self._observation_service.context_for_taxon(
                        projection.candidate_taxon_public_id
                    )
                    was_first = bool(before is not None and before.is_first_observation)
                self._service.accept(public_id, **kwargs)
                after = None
                if projection is not None and self._observation_service is not None:
                    after = self._observation_service.context_for_taxon(
                        projection.candidate_taxon_public_id
                    )
                if after is not None:
                    heading = "First observation" if was_first else "Observation updated"
                    text = (
                        (
                            "This is your first confirmed observation of this taxon.\n\n"
                            if was_first
                            else ""
                        )
                        + f"Personal total: {after.confirmed_observations} observation(s)\n"
                        + f"Supporting photographs: {after.evidence_photos}\n"
                        + f"Countries: {', '.join(after.country_codes) or '—'}"
                    )
                    QMessageBox.information(self, heading, text)
            elif action == "reject":
                self._service.reject(public_id, **kwargs)
            elif action == "defer":
                self._service.defer(public_id, **kwargs)
            elif action == "reverse":
                self._service.reverse_acceptance(public_id, **kwargs)
            else:
                raise ValueError(f"unsupported action: {action}")
            self.refresh()
            messages = {
                "accept": "Suggestion accepted and enrichment recorded.",
                "reject": "Suggestion rejected.",
                "defer": "Suggestion deferred.",
                "reverse": "Acceptance reversed; suggestion returned to pending.",
            }
            self._status.setText(messages[action])
        except Exception as exc:
            QMessageBox.critical(self, "AI Review", str(exc))

    def _selected_id(self) -> str | None:
        item = self._list.currentItem()
        return None if item is None else str(item.data(Qt.ItemDataRole.UserRole))

    def _advance_to_next_pending_photo(self, completed_asset_public_id: str) -> None:
        page = self._service.page(
            filter=ReviewFilter(state="pending"),
            cursor=None,
            page_size=500,
        )
        target = next(
            (item for item in page.items if item.asset_public_id != completed_asset_public_id),
            None,
        )
        self._current_asset_public_id = None if target is None else target.asset_public_id
        self.refresh()
        if target is not None:
            self._select_review_item(target.public_id)

    def _select_review_item(self, public_id: str) -> bool:
        """Select a visible review item by public id after a refresh."""
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None and str(item.data(Qt.ItemDataRole.UserRole)) == public_id:
                self._list.setCurrentRow(row)
                return True
        return False

    def _select_next(self) -> None:
        if self._list.count():
            self._list.setCurrentRow(min(self._list.count() - 1, self._list.currentRow() + 1))

    def _select_previous(self) -> None:
        if self._list.count():
            self._list.setCurrentRow(max(0, self._list.currentRow() - 1))
