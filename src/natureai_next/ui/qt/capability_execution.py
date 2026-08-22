"""Manifest-driven Qt dialog for producer-neutral capability execution."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from natureai_next.application.capability_execution import CapabilityChoice, validate_parameters
from natureai_next.synthesis_core.contracts import InputKind, ParameterDefinition

try:
    from PySide6.QtCore import QTimer, Qt, Signal
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFormLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QLineEdit,
        QMessageBox,
        QSpinBox,
        QProgressBar,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QHBoxLayout,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


@dataclass(frozen=True, slots=True)
class CapabilityDialogRequest:
    capability_id: str
    input_kind: InputKind
    input_path: Path | None
    parameters: Mapping[str, Any]
    structured_input: Mapping[str, Any] | None
    region_classifier_id: str | None = None
    additional_capability_ids: tuple[str, ...] = ()


class CapabilityExecutionDialog(QDialog):
    """Build execution controls entirely from capability descriptors."""

    def __init__(
        self,
        choices: Sequence[CapabilityChoice],
        *,
        input_kind: InputKind,
        input_path: Path | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Run enrichment capability")
        self.resize(520, 520)
        self._choices = tuple(choices)
        self._input_kind = input_kind
        self._input_path = input_path
        self._controls: dict[str, QWidget] = {}
        self._definitions: tuple[ParameterDefinition, ...] = ()
        self._request: CapabilityDialogRequest | None = None

        self._capability = QComboBox()
        for choice in self._choices:
            suffix = "" if choice.available else f" — {choice.reason or 'unavailable'}"
            self._capability.addItem(
                choice.descriptor.display_name + suffix, choice.descriptor.capability_id
            )
            if not choice.available:
                index = self._capability.count() - 1
                model_item = self._capability.model().item(index)
                if model_item is not None:
                    model_item.setEnabled(False)
        self._capability.currentIndexChanged.connect(self._rebuild_parameters)
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._source = QLabel(str(input_path) if input_path else "No local input file selected")
        self._source.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._parameter_host = QWidget()
        self._parameter_form = QFormLayout(self._parameter_host)
        self._structured = QTextEdit()
        self._structured.setPlaceholderText(
            'Optional structured JSON object. Example: {"events":[{"start_seconds":0,"end_seconds":1.5,"label":"call"}]}'
        )
        self._structured.setMaximumHeight(130)
        self._classify_regions = QCheckBox("Classify every detected region")
        self._region_classifier = QComboBox()
        self._additional = QListWidget()
        self._additional.setMaximumHeight(130)
        self._additional.setToolTip(
            "Checked capabilities run as independent producer-neutral enrichments using their defaults."
        )
        for choice in self._choices:
            if not choice.available:
                continue
            item = QListWidgetItem(choice.descriptor.display_name)
            item.setData(Qt.ItemDataRole.UserRole, choice.descriptor.capability_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._additional.addItem(item)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Run
            if hasattr(QDialogButtonBox.StandardButton, "Run")
            else QDialogButtonBox.StandardButton.Ok
        )
        # Qt has no Run standard button in some bindings; ensure a conventional OK/Cancel pair.
        buttons.setStandardButtons(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Run")
        buttons.accepted.connect(self._accept_request)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Capability", self._capability)
        form.addRow("Input type", QLabel(input_kind.value.title()))
        form.addRow("Source", self._source)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._status)
        layout.addWidget(QLabel("Parameters"))
        layout.addWidget(self._parameter_host)
        layout.addWidget(QLabel("Structured input (optional)"))
        layout.addWidget(self._structured)
        layout.addWidget(self._classify_regions)
        layout.addWidget(self._region_classifier)
        layout.addWidget(QLabel("Additional enrichments (optional)"))
        layout.addWidget(self._additional)
        layout.addStretch(1)
        layout.addWidget(buttons)
        self._rebuild_parameters()

    @property
    def request(self) -> CapabilityDialogRequest | None:
        return self._request

    def _current_choice(self) -> CapabilityChoice | None:
        capability_id = self._capability.currentData()
        return next(
            (
                choice
                for choice in self._choices
                if choice.descriptor.capability_id == capability_id
            ),
            None,
        )

    def _clear_form(self) -> None:
        while self._parameter_form.rowCount():
            self._parameter_form.removeRow(0)
        self._controls.clear()

    def _rebuild_parameters(self) -> None:
        self._clear_form()
        choice = self._current_choice()
        if choice is None:
            self._definitions = ()
            self._status.setText("No compatible capability is installed.")
            return
        descriptor = choice.descriptor
        classifiers = tuple(
            item for item in self._choices
            if "taxonomy_candidate" in item.descriptor.outputs
            and self._input_kind in item.descriptor.inputs
            and item.available
        )
        pipeline_available = (
            self._input_kind is InputKind.PHOTO
            and "bounding_box" in descriptor.outputs
            and bool(classifiers)
        )
        self._region_classifier.clear()
        for item in classifiers:
            self._region_classifier.addItem(
                item.descriptor.display_name, item.descriptor.capability_id
            )
        self._classify_regions.setVisible(pipeline_available)
        self._region_classifier.setVisible(pipeline_available)
        self._classify_regions.setChecked(pipeline_available)
        self._definitions = descriptor.parameters
        mode = "offline" if descriptor.offline else "runtime-dependent"
        self._status.setText(
            f"{descriptor.display_name} {descriptor.version} • {mode} • outputs: "
            + ", ".join(sorted(descriptor.outputs))
        )
        for definition in descriptor.parameters:
            control = self._control_for(definition)
            label = definition.name.replace("_", " ").title()
            if definition.required:
                label += " *"
            self._parameter_form.addRow(label, control)
            self._controls[definition.name] = control
        if not descriptor.parameters:
            self._parameter_form.addRow(QLabel("This capability has no configurable parameters."))

    def _control_for(self, definition: ParameterDefinition) -> QWidget:
        if definition.choices:
            combo = QComboBox()
            for choice in definition.choices:
                combo.addItem(str(choice), choice)
            default_index = combo.findData(definition.default)
            if default_index >= 0:
                combo.setCurrentIndex(default_index)
            return combo
        kind = definition.value_type.casefold()
        if kind in {"boolean", "bool"}:
            box = QCheckBox()
            box.setChecked(bool(definition.default))
            return box
        if kind in {"integer", "int"}:
            spin = QSpinBox()
            spin.setRange(
                int(definition.minimum if definition.minimum is not None else -2_147_483_648),
                int(definition.maximum if definition.maximum is not None else 2_147_483_647),
            )
            if definition.default is not None:
                spin.setValue(int(definition.default))
            return spin
        if kind in {"number", "float", "double"}:
            spin = QDoubleSpinBox()
            spin.setDecimals(6)
            spin.setRange(
                float(definition.minimum if definition.minimum is not None else -1e12),
                float(definition.maximum if definition.maximum is not None else 1e12),
            )
            if definition.default is not None:
                spin.setValue(float(definition.default))
            return spin
        edit = QLineEdit()
        if definition.default is not None:
            edit.setText(str(definition.default))
        return edit

    def _values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for definition in self._definitions:
            control = self._controls[definition.name]
            if isinstance(control, QComboBox):
                values[definition.name] = control.currentData()
            elif isinstance(control, QCheckBox):
                values[definition.name] = control.isChecked()
            elif isinstance(control, QSpinBox | QDoubleSpinBox):
                values[definition.name] = control.value()
            elif isinstance(control, QLineEdit):
                values[definition.name] = control.text()
        return validate_parameters(self._definitions, values)

    def _accept_request(self) -> None:
        choice = self._current_choice()
        if choice is None or not choice.available:
            QMessageBox.warning(self, "Capability unavailable", "Select an available capability.")
            return
        try:
            parameters = self._values()
            text = self._structured.toPlainText().strip()
            structured = None
            if text:
                decoded = json.loads(text)
                if not isinstance(decoded, dict):
                    raise ValueError("structured input must be a JSON object")
                structured = decoded
        except (ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Invalid execution request", str(exc))
            return
        self._request = CapabilityDialogRequest(
            choice.descriptor.capability_id,
            self._input_kind,
            self._input_path,
            parameters,
            structured,
            (
                str(self._region_classifier.currentData())
                if self._classify_regions.isVisible()
                and self._classify_regions.isChecked()
                and self._region_classifier.currentData()
                else None
            ),
            tuple(
                str(item.data(Qt.ItemDataRole.UserRole))
                for row in range(self._additional.count())
                for item in (self._additional.item(row),)
                if item.checkState() == Qt.CheckState.Checked
                and str(item.data(Qt.ItemDataRole.UserRole))
                != choice.descriptor.capability_id
            ),
        )
        self.accept()


class CapabilityBatchProgressDialog(QDialog):
    """Independent, non-blocking screen for one library capability batch."""

    completed = Signal(object)

    def __init__(
        self,
        run,
        items: Sequence[tuple[str, str]],
        *,
        capability_name: str,
        library_name: str,
        parent: QWidget | None = None,
    ) -> None:
        # Batch analysis is an independent non-modal window.  Do not give it a
        # transient parent: on Windows a parented QDialog is kept in front of
        # the main window, which prevented users from continuing work while
        # long-running AI jobs were active.
        super().__init__(None)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle(f"{library_name} analysis — {capability_name}")
        self.resize(760, 480)
        self._run = run
        self._item_rows = {public_id: row for row, (public_id, _name) in enumerate(items)}
        self._finished = False

        heading = QLabel(
            f"<h2>{library_name} batch analysis</h2>"
            f"<p>{capability_name} is processing {len(items)} selected file(s) in parallel.</p>"
        )
        heading.setWordWrap(True)
        self._table = QTableWidget(len(items), 2, self)
        self._table.setHorizontalHeaderLabels(("File", "State"))
        self._table.horizontalHeader().setStretchLastSection(True)
        for row, (_public_id, name) in enumerate(items):
            self._table.setItem(row, 0, QTableWidgetItem(name))
            self._table.setItem(row, 1, QTableWidgetItem("Queued"))
        self._progress = QProgressBar(self)
        self._progress.setRange(0, max(1, len(items)))
        self._status = QLabel("Preparing analysis…")
        self._status.setWordWrap(True)
        self._cancel = QPushButton("Cancel remaining")
        self._cancel.clicked.connect(self._cancel_run)
        self._close = QPushButton("Close")
        self._close.setEnabled(False)
        self._close.clicked.connect(self.accept)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self._cancel)
        actions.addWidget(self._close)
        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._progress)
        layout.addWidget(self._status)
        layout.addLayout(actions)
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    @property
    def running(self) -> bool:
        return not self._finished

    def cancel_for_disabled_workspace(self) -> None:
        if self.running:
            self._run.cancel()
            self._status.setText("Library workspace disabled; cancelling active analysis…")

    def _cancel_run(self) -> None:
        self._run.cancel()
        self._cancel.setEnabled(False)
        self._status.setText("Cancellation requested…")

    def _poll(self) -> None:
        states = self._run.item_states
        for public_id, state in states.items():
            row = self._item_rows.get(public_id)
            if row is not None:
                self._table.item(row, 1).setText(state)
        progress = self._run.progress
        total = progress.total or len(self._item_rows)
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(min(progress.current, total))
        self._status.setText(progress.message)
        if not self._run.done:
            return
        self._timer.stop()
        self._finished = True
        self._cancel.setEnabled(False)
        self._close.setEnabled(True)
        try:
            outcome = self._run.result()
        except InterruptedError:
            self._status.setText("Batch analysis cancelled.")
            outcome = None
        except Exception as exc:
            self._status.setText(f"Batch analysis failed: {exc}")
            outcome = None
        else:
            self._status.setText(
                f"Completed {outcome.completed}/{outcome.requested} file(s); "
                f"{len(outcome.failures)} failed."
            )
        self.completed.emit(outcome)

    def closeEvent(self, event) -> None:
        if self.running:
            event.ignore()
            self._status.setText("Cancel the active batch before closing this screen.")
            return
        super().closeEvent(event)
