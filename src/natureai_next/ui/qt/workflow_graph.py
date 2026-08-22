"""Reusable workflow graph and unified enrichment-pipeline presentation widgets."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class WorkflowStep:
    key: str
    title: str
    description: str = ""
    optional: bool = False


class WorkflowGraphWidget(QFrame):
    """Compact accessible directed graph for linear Aperture workflows.

    This deliberately renders with ordinary Qt widgets rather than a scene graph so
    keyboard focus, screen readers and high-DPI scaling remain predictable.
    """

    step_activated = Signal(str)

    def __init__(self, steps: tuple[WorkflowStep, ...] = (), parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("workflowGraph")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._steps = steps
        self._states: dict[str, str] = {}
        self._layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._compact = False
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(5)
        self.setStyleSheet(
            "QFrame#workflowGraph { border: 1px solid palette(mid); border-radius: 7px; }"
            "QPushButton[workflowNode='true'] { text-align: left; padding: 7px; min-width: 0px; }"
            "QPushButton[workflowState='complete'] { font-weight: 600; }"
            "QPushButton[workflowState='active'] { font-weight: 700; border: 2px solid palette(highlight); }"
            "QPushButton[workflowState='optional'] { font-style: italic; }"
        )
        self._rebuild()

    def set_steps(self, steps: tuple[WorkflowStep, ...]) -> None:
        self._steps = steps
        self._rebuild()

    def set_states(self, states: dict[str, str]) -> None:
        """Set state per step: pending, active, complete, optional or unavailable."""
        self._states = dict(states)
        self._rebuild()

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        # Six descriptive stages cannot remain legible in narrow inspector panes.
        # Switch to a vertical graph instead of allowing the final stages to be clipped.
        compact = self.width() < 760
        if compact != self._compact:
            self._compact = compact
            self._layout.setDirection(
                QBoxLayout.Direction.TopToBottom
                if compact
                else QBoxLayout.Direction.LeftToRight
            )
            self._rebuild()

    def _rebuild(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, step in enumerate(self._steps):
            if index:
                arrow = QLabel("↓" if self._compact else "→")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setAccessibleName("then")
                self._layout.addWidget(arrow)
            state = self._states.get(step.key, "optional" if step.optional else "pending")
            marker = {"complete": "✓ ", "active": "● ", "unavailable": "× ", "optional": "○ "}.get(state, "")
            label = marker + step.title + ("\nOptional" if step.optional else "")
            node = QPushButton(label)
            node.setProperty("workflowNode", True)
            node.setProperty("workflowState", state)
            node.setToolTip(step.description or step.title)
            node.setAccessibleName(step.title)
            node.setAccessibleDescription((step.description + f" State: {state}.").strip())
            node.setMinimumWidth(0)
            node.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            node.clicked.connect(lambda _checked=False, key=step.key: self.step_activated.emit(key))
            self._layout.addWidget(node, 0 if self._compact else 1)


ENRICHMENT_PIPELINE_STEPS = (
    WorkflowStep("media", "Media evidence", "The immutable photo, video, sound or document."),
    WorkflowStep("ai", "AI analysis", "An installed local model creates versioned suggestions."),
    WorkflowStep("candidate", "Candidate", "A normalized candidate taxon or other enrichment."),
    WorkflowStep("sources", "Knowledge sources", "Optional external or offline corroboration.", optional=True),
    WorkflowStep("review", "Knowledge Base review", "The user reviews evidence and provenance."),
    WorkflowStep("accepted", "Accepted observation", "A user-confirmed authoritative observation."),
)


class EnrichmentPipelineWidget(QWidget):
    """One shared presentation of Aperture's producer-neutral enrichment lifecycle."""

    stage_activated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = QLabel("<b>Enrichment pipeline</b>")
        self._summary = QLabel("Select media to inspect its enrichment path.")
        self._summary.setWordWrap(True)
        self._graph = WorkflowGraphWidget(ENRICHMENT_PIPELINE_STEPS, self)
        self._graph.step_activated.connect(self.stage_activated)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._title)
        layout.addWidget(self._graph)
        layout.addWidget(self._summary)
        self.set_counts(0, 0, 0)

    def set_subject(self, media_type: str, public_id: str) -> None:
        readable = media_type.replace("_", " ").title()
        self._title.setText(f"<b>{readable} enrichment pipeline</b>")
        self._summary.setToolTip(public_id)

    def set_counts(self, pending: int, accepted: int, rejected: int) -> None:
        states = {"media": "complete"}
        if pending or accepted or rejected:
            states.update({"ai": "complete", "candidate": "complete", "review": "active" if pending else "complete"})
        if accepted:
            states["accepted"] = "complete"
        states["sources"] = "optional"
        self._graph.set_states(states)
        self._summary.setText(
            f"{pending} pending · {accepted} accepted · {rejected} rejected. "
            "Knowledge-source corroboration is optional and never replaces user review."
        )
