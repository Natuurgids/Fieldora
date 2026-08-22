"""Interactive facility floorplan viewer/editor for Fieldora Operations.

The widget deliberately treats ``ops_locations`` as authoritative.  Geometry is
only a visual representation of those records and is persisted through
``OperationsAssetService``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

try:  # PySide6 ships QtSvg in normal desktop builds, but keep a graceful fallback.
    from PySide6.QtSvg import QSvgRenderer
except ImportError:  # pragma: no cover - minimal GUI installations
    QSvgRenderer = None

from natureai_next.application.operations_assets import OperationsAssetService


class FloorplanCanvas(QWidget):
    """Render an operational drawing with clickable normalized geometry."""

    location_selected = Signal(str)
    geometry_created = Signal(str)

    def __init__(self, service: OperationsAssetService, *, actor: str = "local-user", parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.actor = actor
        self.drawing_id = ""
        self.drawing: dict[str, Any] = {}
        self.geometry: list[dict[str, Any]] = []
        self.highlight_location_id = ""
        self.draw_location_id = ""
        self.draw_mode = "select"
        self._draft: list[QPointF] = []
        self._pixmap = QPixmap()
        self._svg = None
        self.setMinimumSize(520, 360)
        self.setMouseTracking(True)
        self.setToolTip("Click a mapped location. In edit mode, click points on the plan and finish a polygon with a double-click.")

    def set_drawing(self, drawing_id: str) -> None:
        self.drawing_id = str(drawing_id or "")
        self.drawing = self.service.drawing(self.drawing_id, self.actor) if self.drawing_id else {}
        self.geometry = list(self.service.drawing_markers(self.drawing_id, self.actor)) if self.drawing_id else []
        self._draft.clear()
        self._load_background()
        self.update()

    def set_highlight_location(self, location_id: str | None) -> None:
        self.highlight_location_id = str(location_id or "")
        self.update()

    def begin_geometry(self, location_id: str, geometry_type: str = "polygon") -> None:
        if geometry_type not in {"point", "rectangle", "polygon", "polyline"}:
            raise ValueError(geometry_type)
        self.draw_location_id = str(location_id or "")
        self.draw_mode = geometry_type
        self._draft.clear()
        self.update()

    def cancel_geometry(self) -> None:
        self.draw_location_id = ""
        self.draw_mode = "select"
        self._draft.clear()
        self.update()

    def _background_path(self) -> str:
        return str(
            self.drawing.get("operational_svg_path")
            or self.drawing.get("preview_path")
            or self.drawing.get("file_path")
            or ""
        )

    def _load_background(self) -> None:
        self._pixmap = QPixmap()
        self._svg = None
        path = self._background_path()
        if not path or not Path(path).is_file():
            return
        if Path(path).suffix.casefold() == ".svg" and QSvgRenderer is not None:
            renderer = QSvgRenderer(path)
            if renderer.isValid():
                self._svg = renderer
                return
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self._pixmap = pixmap

    def _content_rect(self) -> QRectF:
        rect = QRectF(self.rect()).adjusted(16, 16, -16, -16)
        if rect.width() <= 0 or rect.height() <= 0:
            return QRectF()
        source_w = float(self.drawing.get("width") or 0)
        source_h = float(self.drawing.get("height") or 0)
        if source_w <= 0 or source_h <= 0:
            if self._svg is not None:
                size = self._svg.defaultSize()
                source_w, source_h = float(size.width()), float(size.height())
            elif not self._pixmap.isNull():
                source_w, source_h = float(self._pixmap.width()), float(self._pixmap.height())
        if source_w <= 0 or source_h <= 0:
            return rect
        scale = min(rect.width() / source_w, rect.height() / source_h)
        width, height = source_w * scale, source_h * scale
        return QRectF(rect.center().x() - width / 2, rect.center().y() - height / 2, width, height)

    @staticmethod
    def _payload(row: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = json.loads(str(row.get("geometry_json") or "{}"))
            return payload if isinstance(payload, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    def _normalized_points(self, row: dict[str, Any]) -> list[QPointF]:
        payload = self._payload(row)
        coords = payload.get("coordinates") or []
        points: list[QPointF] = []
        for item in coords:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    points.append(QPointF(float(item[0]), float(item[1])))
                except (TypeError, ValueError):
                    pass
        if points:
            return points
        # Compatibility with old point/rectangle markers.
        try:
            x, y = float(row.get("x") or 0), float(row.get("y") or 0)
            w, h = float(row.get("width") or 0), float(row.get("height") or 0)
        except (TypeError, ValueError):
            return []
        if str(row.get("coordinate_space") or "") == "normalized":
            if w or h:
                return [QPointF(x, y), QPointF(x + w, y + h)]
            return [QPointF(x, y)]
        return []

    def _to_canvas(self, point: QPointF) -> QPointF:
        rect = self._content_rect()
        return QPointF(rect.left() + point.x() * rect.width(), rect.top() + point.y() * rect.height())

    def _to_normalized(self, point: QPointF) -> QPointF | None:
        rect = self._content_rect()
        if not rect.contains(point) or rect.width() <= 0 or rect.height() <= 0:
            return None
        return QPointF((point.x() - rect.left()) / rect.width(), (point.y() - rect.top()) / rect.height())

    def _path_for(self, row: dict[str, Any]) -> QPainterPath:
        points = self._normalized_points(row)
        path = QPainterPath()
        if not points:
            return path
        kind = str(row.get("geometry_type") or self._payload(row).get("type") or "point")
        canvas = [self._to_canvas(point) for point in points]
        if kind == "point":
            p = canvas[0]
            path.addEllipse(p, 7, 7)
        elif kind == "rectangle" and len(canvas) >= 2:
            path.addRect(QRectF(canvas[0], canvas[1]).normalized())
        else:
            path.moveTo(canvas[0])
            for point in canvas[1:]:
                path.lineTo(point)
            if kind == "polygon":
                path.closeSubpath()
        return path

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#11181b"))
        content = self._content_rect()
        painter.fillRect(content, QColor("#eef1ed"))
        if self._svg is not None:
            self._svg.render(painter, content)
        elif not self._pixmap.isNull():
            painter.drawPixmap(content.toRect(), self._pixmap)
        else:
            painter.setPen(QPen(QColor("#a9b6b2"), 1))
            painter.drawText(content, Qt.AlignmentFlag.AlignCenter, "No operational SVG/preview available")

        for row in self.geometry:
            path = self._path_for(row)
            if path.isEmpty():
                continue
            selected = str(row.get("location_id") or "") == self.highlight_location_id
            painter.setPen(QPen(QColor("#d08a2f") if selected else QColor("#2b7f58"), 4 if selected else 2))
            painter.setBrush(QColor(208, 138, 47, 65) if selected else QColor(43, 127, 88, 40))
            painter.drawPath(path)

        if self._draft:
            painter.setPen(QPen(QColor("#d08a2f"), 2, Qt.PenStyle.DashLine))
            path = QPainterPath(self._to_canvas(self._draft[0]))
            for point in self._draft[1:]:
                path.lineTo(self._to_canvas(point))
            painter.drawPath(path)

    def _row_at(self, point: QPointF) -> dict[str, Any] | None:
        # Reverse order gives visually topmost geometry first.
        for row in reversed(self.geometry):
            path = self._path_for(row)
            if path.contains(point) or path.boundingRect().adjusted(-5, -5, 5, 5).contains(point):
                return row
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        point = QPointF(event.position())
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        if self.draw_mode == "select":
            row = self._row_at(point)
            if row and row.get("location_id"):
                self.set_highlight_location(str(row["location_id"]))
                self.location_selected.emit(str(row["location_id"]))
            return
        normalized = self._to_normalized(point)
        if normalized is None or not self.draw_location_id:
            return
        self._draft.append(normalized)
        if self.draw_mode == "point":
            self._commit_draft()
        elif self.draw_mode == "rectangle" and len(self._draft) >= 2:
            self._commit_draft()
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.draw_mode in {"polygon", "polyline"}:
            normalized = self._to_normalized(QPointF(event.position()))
            if normalized is not None and (not self._draft or normalized != self._draft[-1]):
                self._draft.append(normalized)
            minimum = 3 if self.draw_mode == "polygon" else 2
            if len(self._draft) >= minimum:
                self._commit_draft()
                return
        super().mouseDoubleClickEvent(event)

    def _commit_draft(self) -> None:
        if not self.drawing_id or not self.draw_location_id or not self._draft:
            return
        coordinates = [[point.x(), point.y()] for point in self._draft]
        try:
            geometry_id = self.service.add_floorplan_geometry(
                self.drawing_id,
                actor=self.actor,
                geometry_type=self.draw_mode,
                coordinates=coordinates,
                location_id=self.draw_location_id,
                label=self.service.location_path(self.draw_location_id, self.actor),
            )
        except Exception as exc:  # UI boundary: service errors are user-visible.
            QMessageBox.warning(self, "Floorplan geometry", str(exc))
            return
        location_id = self.draw_location_id
        self.set_drawing(self.drawing_id)
        self.set_highlight_location(location_id)
        self.draw_mode = "select"
        self.draw_location_id = ""
        self.geometry_created.emit(geometry_id)


class FacilityFloorplanDialog(QDialog):
    """Revision-aware floorplan browser with location-to-plan navigation."""

    def __init__(
        self,
        service: OperationsAssetService,
        *,
        actor: str = "local-user",
        drawing_id: str = "",
        location_id: str = "",
        editable: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.actor = actor
        self.editable = editable
        self.setWindowTitle("Facility floorplan")
        self.resize(1120, 720)

        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Revision"))
        self.revisions = QComboBox()
        self.revisions.currentIndexChanged.connect(self._drawing_changed)
        top.addWidget(self.revisions, 1)
        self.status = QLabel()
        top.addWidget(self.status)
        outer.addLayout(top)

        split = QSplitter()
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(QLabel("Mapped facilities & storage"))
        self.locations = QListWidget()
        self.locations.currentItemChanged.connect(self._location_changed)
        side_layout.addWidget(self.locations, 1)
        self.draw_polygon = QPushButton("Draw polygon for selected location")
        self.draw_polygon.clicked.connect(self._begin_polygon)
        self.draw_polygon.setEnabled(editable)
        side_layout.addWidget(self.draw_polygon)
        self.cancel = QPushButton("Cancel drawing")
        self.cancel.clicked.connect(lambda: self.canvas.cancel_geometry())
        self.cancel.setEnabled(editable)
        side_layout.addWidget(self.cancel)
        split.addWidget(side)

        self.canvas = FloorplanCanvas(service, actor=actor)
        self.canvas.location_selected.connect(self._select_location)
        self.canvas.geometry_created.connect(lambda _identity: self._reload_locations())
        split.addWidget(self.canvas)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 4)
        outer.addWidget(split, 1)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(close)
        outer.addLayout(row)

        self._load_revisions(drawing_id=drawing_id, location_id=location_id)

    def _load_revisions(self, *, drawing_id: str, location_id: str) -> None:
        drawings = list(self.service.drawings(self.actor))
        chosen = drawing_id
        if not chosen and location_id:
            context = self.service.location_drawing_context(location_id, actor=self.actor, include_planned=True)
            chosen = str(context.get("id") or "") if context else ""
        self.revisions.blockSignals(True)
        self.revisions.clear()
        selected_index = 0
        for index, drawing in enumerate(drawings):
            label = f"{drawing['title']} · {drawing.get('version') or 'unversioned'} · {drawing.get('status') or 'draft'}"
            self.revisions.addItem(label, str(drawing["id"]))
            if str(drawing["id"]) == chosen:
                selected_index = index
        self.revisions.setCurrentIndex(selected_index if drawings else -1)
        self.revisions.blockSignals(False)
        self._drawing_changed(self.revisions.currentIndex())
        if location_id:
            self._select_location(location_id)

    def _drawing_changed(self, _index: int) -> None:
        drawing_id = str(self.revisions.currentData() or "")
        if not drawing_id:
            self.canvas.set_drawing("")
            self.locations.clear()
            self.status.setText("No drawing")
            return
        self.canvas.set_drawing(drawing_id)
        drawing = self.canvas.drawing
        self.status.setText(f"{drawing.get('status', 'draft')} · {drawing.get('effective_at') or 'no effective date'}")
        self._reload_locations()

    def _reload_locations(self) -> None:
        selected = self.canvas.highlight_location_id
        self.locations.blockSignals(True)
        self.locations.clear()
        drawing_id = str(self.revisions.currentData() or "")
        for row in self.service.locations_on_drawing(drawing_id, self.actor) if drawing_id else ():
            item = QListWidgetItem(self.service.location_path(str(row["id"]), self.actor))
            item.setData(Qt.ItemDataRole.UserRole, str(row["id"]))
            self.locations.addItem(item)
            if str(row["id"]) == selected:
                self.locations.setCurrentItem(item)
        # Make unmapped canonical locations available to editors too.
        if self.editable:
            mapped = {str(self.locations.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.locations.count())}
            for row in self.service.locations(self.actor):
                if str(row["id"]) in mapped:
                    continue
                item = QListWidgetItem("○ " + self.service.location_path(str(row["id"]), self.actor))
                item.setData(Qt.ItemDataRole.UserRole, str(row["id"]))
                self.locations.addItem(item)
        self.locations.blockSignals(False)

    def _location_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        location_id = str(current.data(Qt.ItemDataRole.UserRole) or "") if current else ""
        self.canvas.set_highlight_location(location_id)

    def _select_location(self, location_id: str) -> None:
        self.canvas.set_highlight_location(location_id)
        for index in range(self.locations.count()):
            item = self.locations.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == location_id:
                self.locations.setCurrentItem(item)
                self.locations.scrollToItem(item)
                break

    def _begin_polygon(self) -> None:
        item = self.locations.currentItem()
        if item is None:
            QMessageBox.information(self, "Floorplan", "Select a location first.")
            return
        self.canvas.begin_geometry(str(item.data(Qt.ItemDataRole.UserRole)), "polygon")
