"""Reusable Qt components for canonical Aperture enrichment."""

from __future__ import annotations

from html import escape

from natureai_next.application.enrichment_ui import (
    EnrichmentWorkspaceController,
    EnrichmentWorkspacePresentation,
)
from natureai_next.domain.enrichment import SubjectRef
from natureai_next.ui.enrichment.interaction import OverlayScene, build_overlay_scene
from natureai_next.ui.qt.workflow_graph import EnrichmentPipelineWidget

try:
    from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, Signal, Slot
    from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen, QPolygonF
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QPushButton,
        QSizePolicy,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


class EnrichmentSummaryPanel(QFrame):
    collapse_toggled = Signal(bool)

    def __init__(self, *, collapsible: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._label = QLabel("No enrichment loaded")
        self._label.setWordWrap(False)
        self._toggle = QPushButton("Collapse details")
        self._toggle.setCheckable(True)
        self._toggle.setToolTip("Fold the lower review area to one compact line")
        self._toggle.setVisible(collapsible)
        self._toggle.toggled.connect(self.collapse_toggled)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 8, 5)
        layout.addWidget(self._label)
        layout.addStretch(1)
        layout.addWidget(self._toggle)

    def set_presentation(self, presentation: EnrichmentWorkspacePresentation) -> None:
        self._label.setText(
            f"Pending: {presentation.pending_count}  •  Accepted: {presentation.accepted_count}  "
            f"•  Rejected: {presentation.rejected_count}"
        )

    def set_collapsed(self, collapsed: bool) -> None:
        self._toggle.blockSignals(True)
        self._toggle.setChecked(collapsed)
        self._toggle.setText("Expand details" if collapsed else "Collapse details")
        self._toggle.setToolTip(
            "Restore the lower review area"
            if collapsed
            else "Fold the lower review area to one compact line"
        )
        self._toggle.blockSignals(False)


class ProvenancePanel(QTextBrowser):
    def show_fields(self, fields: tuple[tuple[str, str], ...]) -> None:
        if not fields:
            self.setHtml("<p>No source snapshot available.</p>")
            return
        rows = "".join(
            f"<tr><th align='left'>{escape(name)}</th><td>{escape(value)}</td></tr>"
            for name, value in fields
        )
        self.setHtml(f"<table>{rows}</table>")


class CanonicalOverlayCanvas(QWidget):
    """Interactive producer-neutral canvas for spatial and temporal canonical shapes."""

    region_selected = Signal(str)
    time_selected = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = OverlayScene("summary", ())
        self._selected_region_id: str | None = None
        self.setMinimumHeight(120)
        self.setMouseTracking(True)

    def set_scene(self, scene: OverlayScene) -> None:
        self._scene = scene
        self._selected_region_id = None
        self.update()

    def select_region(self, region_id: str) -> None:
        if region_id != self._selected_region_id:
            self._selected_region_id = region_id
            self.update()

    def set_playback_position(self, seconds: float) -> None:
        region = self._scene.region_at_time(seconds)
        selected = None if region is None else region.region_id
        if selected != self._selected_region_id:
            self._selected_region_id = selected
            self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(31, 37, 34))
        for region in self._scene.regions:
            selected = region.region_id == self._selected_region_id
            pen = QPen(QColor(232, 245, 233) if selected else QColor(151, 188, 166))
            pen.setWidth(3 if selected else 2)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(111, 143, 125, 85)))
            if region.points:
                polygon = QPolygonF(
                    [
                        QPointF(point[0] * self.width(), point[1] * self.height())
                        for point in region.points
                    ]
                )
                painter.drawPolygon(polygon)
            else:
                painter.drawRect(
                    QRectF(
                        region.x * self.width(),
                        region.y * self.height(),
                        region.width * self.width(),
                        region.height * self.height(),
                    )
                )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        x = event.position().x() / self.width()
        y = event.position().y() / self.height()
        region = self._scene.hit_test(x, y)
        if region is None:
            return
        self._selected_region_id = region.region_id
        self.update()
        self.region_selected.emit(region.region_id)
        if region.start_seconds is not None:
            span = max(0.0, (region.end_seconds or region.start_seconds) - region.start_seconds)
            relative = (
                0.0 if region.width <= 0 else max(0.0, min(1.0, (x - region.x) / region.width))
            )
            self.time_selected.emit(region.start_seconds + span * relative)


class CanonicalEnrichmentPanel(QWidget):
    """Generic subject panel selected by canonical output shape, never model name."""

    review_completed = Signal(str, str)
    visualization_region_selected = Signal(str, str)
    visualization_time_selected = Signal(str, float)
    overlay_scene_changed = Signal(object)

    def __init__(
        self,
        controller: EnrichmentWorkspaceController,
        subject: SubjectRef,
        parent: QWidget | None = None,
        *,
        collapsible: bool = False,
        collapse_settings_key: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._subject = subject
        self._presentation: EnrichmentWorkspacePresentation | None = None
        self._items_by_id = {}
        self._collapsible = collapsible
        self._collapse_settings_key = collapse_settings_key
        self._collapsed = False

        self._pipeline = EnrichmentPipelineWidget(self)
        self._summary = EnrichmentSummaryPanel(collapsible=collapsible)
        self._summary.collapse_toggled.connect(self.set_collapsed)
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._selection_changed)
        self._overlay = CanonicalOverlayCanvas()
        self._overlay.region_selected.connect(self._overlay_region_selected)
        self._overlay.time_selected.connect(self._overlay_time_selected)
        self._visual = QTextBrowser()
        self._visual.setMaximumHeight(100)
        self._detail = QTextBrowser()
        self._provenance = ProvenancePanel()
        self._accept = QPushButton("Accept")
        self._reject = QPushButton("Reject")
        refresh = QPushButton("Refresh")
        self._accept.clicked.connect(self._accept_current)
        self._reject.clicked.connect(self._reject_current)
        refresh.clicked.connect(self.refresh)

        buttons = QHBoxLayout()
        buttons.addWidget(self._accept)
        buttons.addWidget(self._reject)
        buttons.addWidget(refresh)
        buttons.addStretch(1)

        self._body = QWidget(self)
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.addWidget(self._list, 2)
        body_layout.addWidget(self._overlay, 1)
        body_layout.addWidget(self._visual, 1)
        body_layout.addWidget(self._detail, 1)
        body_layout.addWidget(QLabel("Provenance"))
        body_layout.addWidget(self._provenance, 1)
        body_layout.addLayout(buttons)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._pipeline)
        layout.addWidget(self._summary)
        layout.addWidget(self._body, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.refresh()
        if collapsible and collapse_settings_key:
            collapsed = bool(QSettings().value(collapse_settings_key, False, type=bool))
            self.set_collapsed(collapsed)

    @Slot(bool)
    def set_collapsed(self, collapsed: bool) -> None:
        """Fold or restore the detail body without changing its data or controls."""
        if not self._collapsible:
            return
        self._collapsed = bool(collapsed)
        self._body.setVisible(not self._collapsed)
        self._summary.set_collapsed(self._collapsed)
        if self._collapsed:
            # The pipeline remains visible when details are folded.  Include it in
            # the fixed height; otherwise Qt clips the pipeline/summary beneath the
            # Library selection bar and there is no way to reveal the hidden text.
            spacing = self.layout().spacing() if self.layout() is not None else 0
            compact_height = (
                self._pipeline.sizeHint().height()
                + self._summary.sizeHint().height()
                + spacing
            )
            self.setMinimumHeight(compact_height)
            self.setMaximumHeight(compact_height)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if self._collapse_settings_key:
            QSettings().setValue(self._collapse_settings_key, self._collapsed)
        self.updateGeometry()

    def is_collapsed(self) -> bool:
        return self._collapsed

    @Slot()
    def refresh(self) -> None:
        self._show(self._controller.load(self._subject))

    def set_subject(self, subject: SubjectRef) -> None:
        self._subject = subject
        subject_type = getattr(subject.subject_type, "value", str(subject.subject_type))
        self._pipeline.set_subject(str(subject_type), subject.public_id)
        self.refresh()

    def _show(self, presentation: EnrichmentWorkspacePresentation) -> None:
        self._presentation = presentation
        self._summary.set_presentation(presentation)
        self._pipeline.set_counts(presentation.pending_count, presentation.accepted_count, presentation.rejected_count)
        self._items_by_id = {item.enrichment_id: item for item in presentation.items}
        selected_id = self._current_id()
        self._list.clear()
        for item in presentation.items:
            row = QListWidgetItem(f"{item.title}  [{item.component}]")
            row.setData(Qt.ItemDataRole.UserRole, item.enrichment_id)
            self._list.addItem(row)
            if item.enrichment_id == selected_id:
                self._list.setCurrentItem(row)
        if self._list.currentItem() is None and self._list.count():
            self._list.setCurrentRow(0)
        if not presentation.items:
            self._overlay.set_scene(OverlayScene("summary", ()))
            self._visual.setHtml("<p>No visualization available.</p>")
            self._detail.setHtml("<p>No enrichment for this subject.</p>")
            self._provenance.show_fields(())
            self._accept.setEnabled(False)
            self._reject.setEnabled(False)

    @Slot(QListWidgetItem, QListWidgetItem)
    def _selection_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        item = (
            None
            if current is None
            else self._items_by_id.get(current.data(Qt.ItemDataRole.UserRole))
        )
        if item is None:
            return
        fields = "".join(
            f"<tr><th align='left'>{escape(name)}</th><td>{escape(value)}</td></tr>"
            for name, value in item.fields
        )
        scene = build_overlay_scene(item.enrichment_id, item.visualization)
        self._overlay.set_scene(scene)
        self.overlay_scene_changed.emit(scene)
        self._visual.setHtml(_visualization_html(item.component, item.visualization))
        self._detail.setHtml(f"<h3>{escape(item.title)}</h3><table>{fields}</table>")
        self._provenance.show_fields(item.provenance)
        self._accept.setEnabled(item.can_accept)
        self._reject.setEnabled(item.can_reject)

    @Slot()
    def _accept_current(self) -> None:
        enrichment_id = self._current_id()
        if enrichment_id:
            self._show(self._controller.accept(self._subject, enrichment_id))
            self.review_completed.emit(enrichment_id, "accepted")

    @Slot()
    def _reject_current(self) -> None:
        enrichment_id = self._current_id()
        if enrichment_id:
            self._show(self._controller.reject(self._subject, enrichment_id))
            self.review_completed.emit(enrichment_id, "rejected")

    def _current_id(self) -> str | None:
        current = self._list.currentItem()
        return None if current is None else str(current.data(Qt.ItemDataRole.UserRole))

    def set_playback_position(self, seconds: float) -> None:
        """Synchronize temporal canonical selection with an owning media player."""
        self._overlay.set_playback_position(seconds)

    @Slot(str)
    def select_visualization_region(self, region_id: str) -> None:
        """Synchronize an owning viewer selection back into the canonical panel."""
        self._overlay.select_region(region_id)
        enrichment_id = self._current_id()
        if enrichment_id:
            self.visualization_region_selected.emit(enrichment_id, region_id)

    @Slot(str)
    def _overlay_region_selected(self, region_id: str) -> None:
        enrichment_id = self._current_id()
        if enrichment_id:
            self.visualization_region_selected.emit(enrichment_id, region_id)

    @Slot(float)
    def _overlay_time_selected(self, seconds: float) -> None:
        enrichment_id = self._current_id()
        if enrichment_id:
            self.visualization_time_selected.emit(enrichment_id, seconds)


def _visualization_html(component: str, data: object) -> str:
    payload = dict(data or {})
    kind = str(payload.get("kind") or component)
    if kind == "spatial":
        boxes = payload.get("boxes") or ()
        if boxes:
            box = dict(boxes[0])
            left = int(float(box.get("x", 0)) * 100)
            top = int(float(box.get("y", 0)) * 100)
            width = max(1, int(float(box.get("width", 0)) * 100))
            height = max(1, int(float(box.get("height", 0)) * 100))
            return (
                "<div style='position:relative;width:100%;height:110px;background:#202622;border:1px solid #59675f'>"
                f"<div style='position:absolute;left:{left}%;top:{top}%;width:{width}%;height:{height}%;"
                "border:2px solid #c8e6c9'></div></div>"
            )
        return "<p>Segmentation geometry is available for the subject overlay.</p>"
    if kind in {"timeline", "time-frequency"}:
        start = float(payload.get("start_seconds") or 0)
        end = float(payload.get("end_seconds") or start)
        duration = max(end, 1.0)
        left = int((start / duration) * 100)
        width = max(2, int(((end - start) / duration) * 100))
        frequency = ""
        if payload.get("low_hz") is not None or payload.get("high_hz") is not None:
            frequency = f"<p>{escape(str(payload.get('low_hz') or 0))}–{escape(str(payload.get('high_hz') or '—'))} Hz</p>"
        return (
            f"<p>{start:.3f}s – {end:.3f}s</p>"
            "<div style='position:relative;width:100%;height:28px;background:#202622'>"
            f"<div style='position:absolute;left:{left}%;width:{width}%;height:100%;background:#6f8f7d'></div></div>"
            + frequency
        )
    if kind == "transcript":
        speaker = payload.get("speaker")
        prefix = f"<b>{escape(str(speaker))}:</b> " if speaker else ""
        return f"<blockquote>{prefix}{escape(str(payload.get('text') or ''))}</blockquote>"
    if kind == "document-region":
        return (
            f"<p><b>Page {int(payload.get('page') or 1)}</b> · "
            f"{escape(str(payload.get('region_type') or 'region'))}</p>"
            f"<p>{escape(str(payload.get('text') or ''))}</p>"
        )
    return f"<p>{escape(component.replace('-', ' ').title())}</p>"
