"""Knowledge-source hub kept deliberately separate from executable AI models."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from natureai_next.ui.qt.workflow_graph import EnrichmentPipelineWidget

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class KnowledgeSourceDescriptor:
    name: str
    purpose: str
    availability: str
    route: str
    action: str
    optional: bool = True


SOURCES = (
    KnowledgeSourceDescriptor(
        "GBIF",
        "Independent taxonomy and regional occurrence evidence used to enrich candidate taxa.",
        "Built-in optional source; local Darwin Core and regional packages are supported.",
        "Taxonomy Resources",
        "Configure GBIF…",
    ),
    KnowledgeSourceDescriptor(
        "iNaturalist",
        "Community observations and identifications supplied through installed source packages.",
        "Optional source integration; availability depends on installed connectors or offline bundles.",
        "Enrichment Sources",
        "Manage sources…",
    ),
    KnowledgeSourceDescriptor(
        "eBird",
        "Bird distribution and checklist evidence supplied through installed source packages.",
        "Optional source integration; no AI model depends on it.",
        "Enrichment Sources",
        "Manage sources…",
    ),
    KnowledgeSourceDescriptor(
        "Xeno-canto",
        "Reference recordings used to compare and review acoustic candidates.",
        "Optional reference integration; audio inference remains local and independent.",
        "Manage Integrations",
        "Manage integration…",
    ),
)


class KnowledgeSourcesWorkspace(QWidget):
    """Presents scientific/reference sources without mixing them with AI runtimes."""

    route_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Knowledge Sources</h2>"))
        intro = QLabel(
            "Knowledge sources enrich or corroborate AI candidates. They are optional, remain "
            "independent from executable model packages, and never become Aperture's curated "
            "truth until a user accepts the resulting knowledge record."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        pipeline = EnrichmentPipelineWidget(self)
        pipeline.set_subject("all media", "knowledge-sources")
        layout.addWidget(pipeline)

        grid = QGridLayout()
        for index, source in enumerate(SOURCES):
            card = self._card(source)
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        layout.addStretch(1)

    def _card(self, source: KnowledgeSourceDescriptor) -> QFrame:
        card = QFrame(self)
        card.setFrameShape(QFrame.Shape.StyledPanel)
        body = QVBoxLayout(card)
        heading = QLabel(f"<h3>{source.name}</h3>")
        body.addWidget(heading)
        purpose = QLabel(source.purpose)
        purpose.setWordWrap(True)
        body.addWidget(purpose)
        status = QLabel(f"<b>Status:</b> {source.availability}")
        status.setWordWrap(True)
        body.addWidget(status)
        row = QHBoxLayout()
        optional = QLabel("Optional knowledge source" if source.optional else "Core source")
        optional.setStyleSheet("QLabel { font-style: italic; }")
        row.addWidget(optional)
        row.addStretch(1)
        action = QPushButton(source.action)
        action.clicked.connect(lambda _checked=False, route=source.route: self.route_requested.emit(route))
        row.addWidget(action)
        body.addLayout(row)
        return card
