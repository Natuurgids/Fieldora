"""Asynchronous, keyboard-first full image viewer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from natureai_next.application.enrichment_ui import EnrichmentWorkspaceController

from natureai_next.ports.catalog_queries import AssetDetail
from natureai_next.ui.presentation.viewer import ViewerPresenter

try:
    from PySide6.QtCore import QByteArray, QObject, QPointF, QRectF, Qt, QThread, Signal, Slot
    from PySide6.QtGui import (
        QAction,
        QBrush,
        QColor,
        QKeySequence,
        QPen,
        QPixmap,
        QPolygonF,
        QWheelEvent,
    )
    from PySide6.QtWidgets import (
        QDialog,
        QGraphicsItem,
        QGraphicsPixmapItem,
        QGraphicsPolygonItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsView,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QSplitter,
        QStatusBar,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


class ViewerCatalogService(Protocol):
    def detail(self, public_id: str) -> AssetDetail | None: ...
    def derivative_path(self, public_id: str, kind: str) -> str | None: ...


class ViewerPreviewService(Protocol):
    def load(
        self, *, source_path: Path | None, cached_path: Path | None, max_size: int
    ) -> bytes | None: ...


class _ViewerLoadWorker(QObject):
    ready = Signal(int, str, object, object)
    failed = Signal(int, str, str)

    def __init__(
        self,
        *,
        request_id: int,
        public_id: str,
        catalog: ViewerCatalogService,
        previews: ViewerPreviewService,
    ) -> None:
        super().__init__()
        self._request_id = request_id
        self._public_id = public_id
        self._catalog = catalog
        self._previews = previews

    @Slot()
    def run(self) -> None:
        try:
            detail = self._catalog.detail(self._public_id)
            if detail is None:
                raise LookupError("asset is no longer available")
            cached_value = (
                self._catalog.derivative_path(self._public_id, "preview")
                or self._catalog.derivative_path(self._public_id, "thumbnail")
            )
            data = self._previews.load(
                source_path=Path(detail.primary_path) if detail.primary_path else None,
                cached_path=Path(cached_value) if cached_value else None,
                max_size=4096,
            )
            if not data:
                raise OSError("preview could not be decoded")
            self.ready.emit(self._request_id, self._public_id, detail, data)
        except Exception as exc:
            self.failed.emit(self._request_id, self._public_id, f"{type(exc).__name__}: {exc}")


class ZoomableImageView(QGraphicsView):
    """Image viewer with normalized canonical overlays that follow zoom and pan."""

    zoom_changed = Signal(float)
    overlay_region_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._item = QGraphicsPixmapItem()
        self._scene.addItem(self._item)
        self.setScene(self._scene)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setBackgroundBrush(Qt.GlobalColor.black)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._fit_mode = True
        self._zoom = 1.0
        self._overlay_items: dict[str, QGraphicsItem] = {}
        self._overlay_scene: object | None = None

    def set_image(self, pixmap: QPixmap) -> None:
        self._item.setPixmap(pixmap)
        self._scene.setSceneRect(self._item.boundingRect())
        self._render_overlay_scene()
        self.fit_image()

    def clear_image(self) -> None:
        self.clear_overlay_scene()
        self._item.setPixmap(QPixmap())
        self.resetTransform()
        self._zoom = 1.0
        self.zoom_changed.emit(self._zoom)

    def clear_overlay_scene(self) -> None:
        for item in tuple(self._overlay_items.values()):
            self._scene.removeItem(item)
        self._overlay_items.clear()

    def set_overlay_scene(self, scene: object) -> None:
        """Retain a normalized scene and render it when an image is available."""
        self._overlay_scene = scene
        self._render_overlay_scene()

    def _render_overlay_scene(self) -> None:
        self.clear_overlay_scene()
        pixmap = self._item.pixmap()
        if pixmap.isNull():
            return
        width = float(pixmap.width())
        height = float(pixmap.height())
        for region in tuple(getattr(self._overlay_scene, "regions", ())):
            pen = QPen(QColor(214, 242, 220))
            pen.setWidthF(max(1.0, 2.0 / max(self.transform().m11(), 0.01)))
            brush = QBrush(QColor(83, 143, 103, 70))
            points = tuple(getattr(region, "points", ()) or ())
            if points:
                item = QGraphicsPolygonItem(
                    QPolygonF([QPointF(x * width, y * height) for x, y in points])
                )
            else:
                item = QGraphicsRectItem(
                    QRectF(
                        float(getattr(region, "x", 0.0)) * width,
                        float(getattr(region, "y", 0.0)) * height,
                        float(getattr(region, "width", 0.0)) * width,
                        float(getattr(region, "height", 0.0)) * height,
                    )
                )
            item.setPen(pen)
            item.setBrush(brush)
            item.setData(0, str(getattr(region, "region_id", "")))
            item.setZValue(10.0)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self._scene.addItem(item)
            self._overlay_items[str(getattr(region, "region_id", ""))] = item

    def select_overlay_region(self, region_id: str) -> None:
        for key, item in self._overlay_items.items():
            item.setSelected(key == region_id)

    def mousePressEvent(self, event: object) -> None:
        super().mousePressEvent(event)
        selected = self._scene.selectedItems()
        if selected:
            region_id = str(selected[0].data(0) or "")
            if region_id:
                self.overlay_region_selected.emit(region_id)

    def fit_image(self) -> None:
        if self._item.pixmap().isNull():
            return
        self.resetTransform()
        self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)
        self._fit_mode = True
        self._zoom = self.transform().m11()
        self.zoom_changed.emit(self._zoom)

    def actual_size(self) -> None:
        if self._item.pixmap().isNull():
            return
        self.resetTransform()
        self.centerOn(self._item)
        self._fit_mode = False
        self._zoom = 1.0
        self.zoom_changed.emit(self._zoom)

    def zoom_by(self, multiplier: float) -> None:
        if self._item.pixmap().isNull() or multiplier <= 0:
            return
        target = self._zoom * multiplier
        if target < 0.05 or target > 32.0:
            return
        self.scale(multiplier, multiplier)
        self._fit_mode = False
        self._zoom = target
        self.zoom_changed.emit(self._zoom)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.angleDelta().y() == 0:
            return
        self.zoom_by(1.25 if event.angleDelta().y() > 0 else 0.8)
        event.accept()

    def mouseDoubleClickEvent(self, event: object) -> None:
        if self._fit_mode:
            self.actual_size()
        else:
            self.fit_image()
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        if self._fit_mode:
            self.fit_image()


class ViewerDialog(QDialog):
    """Modeless viewer over the ordering currently materialized in Library."""

    def __init__(
        self,
        *,
        ordered_ids: tuple[str, ...],
        public_id: str,
        catalog: ViewerCatalogService,
        previews: ViewerPreviewService,
        parent: QWidget | None = None,
        enrichment_controller: EnrichmentWorkspaceController | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("NatureAI Next — Viewer")
        self.resize(1280, 860)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._catalog = catalog
        self._previews = previews
        self._presenter = ViewerPresenter()
        self._presenter.open(ordered_ids, public_id)
        self._request_id = 0
        self._threads: set[QThread] = set()
        self._workers: set[QObject] = set()
        self._enrichment_panel = None
        self._content_splitter: QSplitter | None = None

        self._view = ZoomableImageView()
        self._title = QLabel()
        self._title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._position = QLabel()
        self._zoom = QLabel("Fit")
        self._status = QStatusBar()

        self._previous = QPushButton("Previous")
        self._previous.clicked.connect(self.previous)
        self._next = QPushButton("Next")
        self._next.clicked.connect(self.next)
        self._fit = QPushButton("Fit")
        self._fit.clicked.connect(self._view.fit_image)
        self._actual = QPushButton("100%")
        self._actual.clicked.connect(self._view.actual_size)
        self._minus = QPushButton("−")
        self._minus.clicked.connect(lambda: self._view.zoom_by(0.8))
        self._plus = QPushButton("+")
        self._plus.clicked.connect(lambda: self._view.zoom_by(1.25))
        self._view.zoom_changed.connect(lambda factor: self._zoom.setText(f"{factor * 100:.0f}%"))

        toolbar = QHBoxLayout()
        for widget in (
            self._previous,
            self._next,
            self._fit,
            self._actual,
            self._minus,
            self._plus,
        ):
            toolbar.addWidget(widget)
        toolbar.addStretch(1)
        toolbar.addWidget(self._position)
        toolbar.addWidget(self._zoom)

        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addLayout(toolbar)
        content: QWidget = self._view
        if enrichment_controller is not None:
            from natureai_next.domain.enrichment import SubjectRef, SubjectType
            from natureai_next.ui.qt.enrichment import CanonicalEnrichmentPanel

            self._enrichment_panel = CanonicalEnrichmentPanel(
                enrichment_controller, SubjectRef(SubjectType.PHOTO, public_id), self
            )
            self._enrichment_panel.overlay_scene_changed.connect(self._view.set_overlay_scene)
            self._enrichment_panel.visualization_region_selected.connect(
                lambda _enrichment_id, region_id: self._view.select_overlay_region(region_id)
            )
            self._view.overlay_region_selected.connect(
                self._enrichment_panel.select_visualization_region
            )
            self._enrichment_panel.refresh()
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.addWidget(self._view)
            splitter.addWidget(self._enrichment_panel)
            splitter.setChildrenCollapsible(False)
            splitter.setStretchFactor(0, 7)
            splitter.setStretchFactor(1, 3)
            splitter.setSizes([896, 384])
            self._content_splitter = splitter
            content = splitter
        layout.addWidget(content, 1)
        layout.addWidget(self._status)

        self._install_actions()
        self._load_current()

    def _install_actions(self) -> None:
        bindings = (
            ("Previous", "Left", self.previous),
            ("Previous page", "PgUp", self.previous),
            ("Next", "Right", self.next),
            ("Next page", "PgDown", self.next),
            ("First", "Home", self.first),
            ("Last", "End", self.last),
            ("Fit", "F", self._view.fit_image),
            ("Actual", "1", self._view.actual_size),
            ("Zoom in", "+", lambda: self._view.zoom_by(1.25)),
            ("Zoom out", "-", lambda: self._view.zoom_by(0.8)),
        )
        for label, key, callback in bindings:
            action = QAction(label, self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(callback)
            self.addAction(action)

    @Slot()
    def next(self) -> None:
        if self._presenter.next():
            self._load_current()

    @Slot()
    def previous(self) -> None:
        if self._presenter.previous():
            self._load_current()

    @Slot()
    def first(self) -> None:
        if self._presenter.first():
            self._load_current()

    @Slot()
    def last(self) -> None:
        if self._presenter.last():
            self._load_current()

    def _load_current(self) -> None:
        public_id = self._presenter.state.current_id
        if public_id is None:
            return
        self._request_id += 1
        request_id = self._request_id
        self._view.clear_image()
        if self._enrichment_panel is not None:
            from natureai_next.domain.enrichment import SubjectRef, SubjectType

            self._enrichment_panel.set_subject(SubjectRef(SubjectType.PHOTO, public_id))
        self._title.setText("Loading…")
        self._status.showMessage("Loading preview…")
        self._update_navigation()
        thread = QThread(self)
        worker = _ViewerLoadWorker(
            request_id=request_id,
            public_id=public_id,
            catalog=self._catalog,
            previews=self._previews,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.ready.connect(self._ready)
        worker.failed.connect(self._failed)
        worker.ready.connect(thread.quit)
        worker.failed.connect(thread.quit)
        self._track(thread, worker)
        thread.start()

    @Slot(int, str, object, object)
    def _ready(self, request_id: int, public_id: str, detail: AssetDetail, data: bytes) -> None:
        if request_id != self._request_id or public_id != self._presenter.state.current_id:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(QByteArray(data)):
            self._failed(request_id, public_id, "Preview data is invalid")
            return
        self._view.set_image(pixmap)
        filename = Path(detail.primary_path).name if detail.primary_path else public_id
        dimensions = (
            f"{detail.pixel_width} × {detail.pixel_height}"
            if detail.pixel_width and detail.pixel_height
            else "unknown dimensions"
        )
        self._title.setText(f"<b>{detail.title or filename}</b> — {dimensions}")
        self._status.showMessage(detail.primary_path or public_id)

    @Slot(int, str, str)
    def _failed(self, request_id: int, public_id: str, message: str) -> None:
        if request_id != self._request_id or public_id != self._presenter.state.current_id:
            return
        self._title.setText("Preview unavailable")
        self._status.showMessage(message)

    def _update_navigation(self) -> None:
        state = self._presenter.state
        self._previous.setEnabled(state.can_previous)
        self._next.setEnabled(state.can_next)
        self._position.setText(f"{state.index + 1} / {len(state.ordered_ids)}")

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        if self._enrichment_panel is not None:
            self._enrichment_panel.setMaximumWidth(max(280, int(self.width() * 0.30)))

    def closeEvent(self, event: object) -> None:
        # Prevent child QThread destruction while a preview decode is still running.
        self._request_id += 1
        for thread in tuple(self._threads):
            if thread.isRunning():
                thread.quit()
                thread.wait(10000)
        super().closeEvent(event)

    def _track(self, thread: QThread, worker: QObject) -> None:
        self._threads.add(thread)
        self._workers.add(worker)

        def cleanup() -> None:
            self._workers.discard(worker)
            self._threads.discard(thread)

        thread.finished.connect(cleanup)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
