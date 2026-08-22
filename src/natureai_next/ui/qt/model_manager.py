"""Catalog-driven model management UI."""

from __future__ import annotations

import threading
from html import escape

from PySide6.QtCore import QObject, QThread, Signal, Slot
from natureai_next.ui.qt.workflow_graph import WorkflowGraphWidget, WorkflowStep

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class _ModelInstallProgress(QFrame):
    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(104)
        self._label = QLabel("Preparing model installation")
        self._label.setWordWrap(True)
        self._label.setFixedHeight(42)
        self._progress = QProgressBar()
        self._progress.setRange(0, 4)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.cancelled)
        row = QHBoxLayout()
        row.addWidget(self._progress, 1)
        row.addWidget(cancel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(self._label)
        layout.addLayout(row)
        self.hide()

    def setRange(self, minimum: int, maximum: int) -> None:
        self._progress.setRange(minimum, maximum)

    def setValue(self, value: int) -> None:
        self._progress.setValue(value)

    def setLabelText(self, message: str) -> None:
        # Pip lines can contain enormous wheel URLs and dependency chains.
        # Bound the visible status so progress never changes workspace geometry.
        text = " ".join(str(message).split())
        self._label.setText(text if len(text) <= 240 else text[:237] + "…")


class _ModelInstallWorker(QObject):
    progressed = Signal(int, int, str)
    finished = Signal(object, object)

    def __init__(self, manager, key: str, accept_license: bool) -> None:
        super().__init__()
        self._manager = manager
        self._key = key
        self._accept_license = accept_license
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        try:
            result = self._manager.install_model(
                self._key,
                accept_license=self._accept_license,
                progress=lambda current, total, message: self.progressed.emit(
                    current, total, message
                ),
                cancellation=self._cancelled.is_set,
            )
            self.finished.emit(result, None)
        except Exception as exc:  # pragma: no cover - dependency/network/platform dependent
            self.finished.emit(None, exc)


class ModelManagerWorkspace(QWidget):
    def __init__(self, manager, parent=None) -> None:
        super().__init__(parent)
        self._manager = manager
        self._install_thread: QThread | None = None
        self._install_worker: _ModelInstallWorker | None = None
        self._install_progress = _ModelInstallProgress(self)
        self._model = QComboBox()
        for spec in manager.available():
            self._model.addItem(spec.display_name, spec.key)
        current = self._model.findData(manager.active_key)
        if current >= 0:
            self._model.setCurrentIndex(current)
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._workflow_graph = WorkflowGraphWidget(parent=self)
        self._parameters = QWidget()
        self._parameter_layout = QFormLayout(self._parameters)
        self._model.currentIndexChanged.connect(self.refresh)
        activate = QPushButton("Activate")
        activate.clicked.connect(self._activate)
        self._load_model = QPushButton("Load model…")
        self._load_model.clicked.connect(self._install)
        deactivate = QPushButton("Turn off…")
        deactivate.clicked.connect(self._deactivate)
        buttons = QHBoxLayout()
        for button in (activate, self._load_model, deactivate):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Models</h2>"))
        intro = QLabel(
            "Models are discovered from Aperture's external catalog and optional "
            "'aperture.models' package entry points. Load downloads and validates a runtime; "
            "Activate enables the model only for compatible media capabilities. Multiple models "
            "may be active at the same time when they serve Photos, Sounds, Videos, or Documents. "
            "Knowledge Base records the exact model that generated every suggestion."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(self._model)
        layout.addLayout(buttons)
        layout.addWidget(self._install_progress)
        self._status.setTextFormat(self._status.textFormat())
        self._status.setStyleSheet("QLabel { padding: 12px; border: 1px solid palette(mid); border-radius: 6px; }")
        layout.addWidget(self._status)
        layout.addWidget(QLabel("<b>Workflow graph</b>"))
        layout.addWidget(self._workflow_graph)
        layout.addWidget(QLabel("<b>Input parameters</b>"))
        layout.addWidget(self._parameters)
        layout.addStretch(1)
        self.refresh()

    def _key(self) -> str:
        return str(self._model.currentData())

    def _activate(self) -> None:
        key = self._key()
        missing = self._manager.missing_dependencies(key)
        if missing:
            QMessageBox.information(
                self,
                "Model dependencies",
                "Install the missing dependencies before activating this model.",
            )
            return
        self._manager.activate(key)
        self.refresh()

    def _install(self) -> None:
        if self._install_thread is not None:
            return
        key = self._key()
        spec = self._manager.catalog.get(key)
        accepted = not spec.requires_license_acceptance
        if spec.requires_license_acceptance:
            size = (
                f"\n\nEstimated download: approximately {spec.estimated_download_mb:,} MB."
                if spec.estimated_download_mb
                else ""
            )
            answer = QMessageBox.question(
                self,
                "Model licence",
                (
                    f"{spec.display_name}\n\n{spec.license_name}\n"
                    f"{spec.license_url or ''}{size}\n\n"
                    "Download and use this model under those terms?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            accepted = answer == QMessageBox.StandardButton.Yes
        if not accepted:
            return
        thread = QThread(self)
        worker = _ModelInstallWorker(self._manager, key, accepted)
        worker.moveToThread(thread)
        progress = self._install_progress
        progress.setRange(0, 4)
        progress.setValue(0)
        progress.setLabelText(f"Preparing {spec.display_name} installation")
        # Call the thread-safe Event setter directly. A queued call to an object
        # whose worker thread is busy in run() cannot be delivered until run ends.
        try:
            progress.cancelled.disconnect()
        except RuntimeError:
            pass
        progress.cancelled.connect(lambda: worker.cancel())
        worker.progressed.connect(self._install_progressed)
        worker.finished.connect(self._install_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.started.connect(worker.run)
        self._install_thread = thread
        self._install_worker = worker
        self._load_model.setEnabled(False)
        progress.show()
        thread.start()

    @Slot(int, int, str)
    def _install_progressed(self, current: int, total: int, message: str) -> None:
        self._install_progress.setRange(0, total)
        self._install_progress.setValue(current)
        self._install_progress.setLabelText(message)
        self._status.setText(escape(message))

    @Slot(object, object)
    def _install_finished(self, result: object, error: object) -> None:
        self._install_progress.hide()
        if isinstance(error, InterruptedError):
            self._status.setText("Model installation cancelled; no model was published.")
        elif error is not None:
            QMessageBox.warning(self, "Model installation failed", str(error))
        elif result is not None:
            self._manager.activate(result.key)
            QMessageBox.information(
                self,
                "Model ready",
                f"{self._manager.catalog.get(result.key).display_name} passed its health check "
                "and is enabled in compatible Run enrichment model choosers.",
            )
        self._install_thread = None
        self._install_worker = None
        self._load_model.setEnabled(True)
        self.refresh()

    def _deactivate(self) -> None:
        key = self._key()
        answer = QMessageBox.question(
            self,
            "Turn off model",
            "Delete the downloaded model runtime and dependencies too?\n\nYes deletes them. No keeps them for the next activation.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return
        self._manager.deactivate(key, delete_files=answer == QMessageBox.StandardButton.Yes)
        self.refresh()

    def refresh(self) -> None:
        key = self._key()
        spec = self._manager.catalog.get(key)
        missing = self._manager.missing_dependencies(key)
        state = (
            "active for compatible capabilities"
            if key in self._manager.active_keys
            else "not active"
        )
        installed = self._manager.is_installed(key)
        dependencies = "ready" if not missing else "missing: " + ", ".join(missing)
        detail = self._manager.installation_detail(key)
        size = (
            f" · estimated download {spec.estimated_download_mb:,} MB"
            if spec.estimated_download_mb
            else ""
        )
        asset_types = tuple(str(value) for value in spec.input_contract.get("asset_types", ()))
        workspaces = []
        if "photo" in asset_types:
            workspaces.append("Photos → select photo → Run enrichment")
        if "sound" in asset_types:
            workspaces.append("Sounds → select recording → Run enrichment")
        if "video" in asset_types:
            workspaces.append("Videos → select video → Run enrichment")
        if "document" in asset_types:
            workspaces.append("Documents → select document → Run enrichment")
        usage = "; ".join(workspaces) or "No interactive workspace declared"
        enrichment_type = str(spec.output_contract.get("enrichment_type") or "unspecified")
        review_mode = str(spec.output_contract.get("review_mode") or "provider-specific")
        active_for = ", ".join(
            f"{value.title()} {enrichment_type.replace('.', ' ')}" for value in asset_types
        ) or "No compatible media capability declared"
        ui = dict(spec.ui_contract)
        category = str(ui.get("category") or spec.family.replace("-", " ").title())
        purpose = str(ui.get("purpose") or spec.description)
        best_for = tuple(str(value) for value in ui.get("best_for", ()))
        not_for = tuple(str(value) for value in ui.get("not_for", ()))
        works_with = tuple(str(value) for value in ui.get("works_with", ()))
        workflow = tuple(str(value) for value in ui.get("workflow", ()))
        workflow_dependencies = tuple(str(value) for value in ui.get("dependencies", ()))
        produces = tuple(str(value) for value in ui.get("produces", ()))
        if not produces:
            produces = (
                enrichment_type.replace(".", " ").title(),
                f"Knowledge Base review mode: {review_mode.replace('_', ' ')}",
                "Provenance identifying the model, version, and run",
            )

        runtime_health = (
            "Healthy — installed, dependencies ready, and available for compatible workspaces"
            if installed and not missing
            else (
                "Unavailable — required dependencies are missing: " + ", ".join(missing)
                if missing
                else "Not installed — load the model to validate its local runtime"
            )
        )

        def lines(values: tuple[str, ...], empty: str = "None declared") -> str:
            return "<br>".join(f"&bull; {escape(value)}" for value in values) or escape(empty)

        offline_badge = "<b style='color:#65b56f'>● Offline ready</b>" if installed and not missing else "<b style='color:#d0a04b'>○ Install to use offline</b>"
        workflow_html = " &rarr; ".join(f"<b>{escape(value)}</b>" for value in workflow) or "No chained workflow declared"
        graph_steps = tuple(
            WorkflowStep(f"step-{index}", value, "Model catalog workflow stage")
            for index, value in enumerate(workflow)
        )
        if not graph_steps:
            graph_steps = (WorkflowStep("standalone", "Standalone model", "No chained workflow declared"),)
        self._workflow_graph.set_steps(graph_steps)
        self._workflow_graph.set_states({step.key: ("complete" if installed and not missing else "pending") for step in graph_steps})
        self._status.setText(
            f"<h3>{escape(spec.display_name)}</h3>"
            f"<b>Category:</b> {escape(category)} &nbsp; {offline_badge}<br>"
            f"<b>Status:</b> {escape(state)} · {'installed' if installed else 'not installed'} · dependencies {escape(dependencies)}{size}<br><br>"
            f"<b>Purpose</b><br>{escape(purpose)}<br><br>"
            f"<b>Produces</b><br>{lines(produces)}<br><br>"
            f"<b>Best for</b><br>{lines(best_for)}<br><br>"
            f"<b>Not intended for</b><br>{lines(not_for)}<br><br>"
            f"<b>Works with</b><br>{lines(works_with, 'Standalone model')}<br><br>"
            f"<b>Typical workflow</b><br>{workflow_html}<br><br>"
            f"<b>Workflow dependencies</b><br>{lines(workflow_dependencies)}<br><br>"
            f"<b>Offline ready</b><br>{'Yes — the installed runtime executes locally without network access.' if installed and not missing else 'No — install and validate the runtime first.'}<br><br>"
            f"<b>Runtime health</b><br>{escape(runtime_health)}<br>"
            f"{escape(detail) if detail else 'Load Model downloads files and runs a health check before activation.'}<br><br>"
            f"<b>Active for:</b> {escape(active_for)}<br>"
            f"<b>Review mode:</b> {escape(review_mode)}<br>"
            f"<b>Started from:</b> {escape(usage)}<br>"
            f"<b>Licence:</b> {escape(spec.license_name or 'bundled')}"
        )
        self._load_model.setVisible(not spec.built_in)
        while self._parameter_layout.rowCount():
            self._parameter_layout.removeRow(0)
        parameters = dict(spec.input_contract.get("parameters") or {})
        if not parameters:
            self._parameter_layout.addRow(QLabel("No configurable inputs declared."))
        for name, definition in parameters.items():
            self._parameter_layout.addRow(
                str(definition.get("title") or name), self._control(definition)
            )

    @staticmethod
    def _control(definition: dict):
        kind = str(definition.get("type") or "text")
        if kind == "integer":
            control = QSpinBox()
            control.setRange(
                int(definition.get("minimum", -2147483648)),
                int(definition.get("maximum", 2147483647)),
            )
            control.setValue(int(definition.get("default", 0)))
            return control
        if kind == "real":
            control = QDoubleSpinBox()
            control.setRange(
                float(definition.get("minimum", -1e12)), float(definition.get("maximum", 1e12))
            )
            control.setValue(float(definition.get("default", 0)))
            return control
        if kind == "boolean":
            control = QCheckBox()
            control.setChecked(bool(definition.get("default", False)))
            return control
        if kind == "choice":
            control = QComboBox()
            control.addItems([str(value) for value in definition.get("choices", ())])
            return control
        control = QLineEdit(str(definition.get("default", "")))
        return control
