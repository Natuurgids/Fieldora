"""Qt library workspace backed by catalog query and thumbnail services."""

from __future__ import annotations

import html
import json
import os
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from natureai_next.domain.search import StructuredAssetFilters
from natureai_next.ports.catalog_queries import (
    AssetDetail,
    AssetPage,
    BatchReviewTarget,
    MetadataPatch,
    ReviewPatch,
)

try:
    from PySide6.QtCore import (
        QByteArray,
        QAbstractListModel,
        QModelIndex,
        QObject,
        QSettings,
        QSize,
        Qt,
        QThread,
        QTimer,
        Signal,
        Slot,
    )
    from PySide6.QtGui import QIcon, QKeySequence, QPainter, QPixmap, QShortcut
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDateEdit,
        QDialog,
        QDoubleSpinBox,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListView,
        QStyledItemDelegate,
        QMessageBox,
        QProgressDialog,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QStyle,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


class CatalogApplicationService(Protocol):
    def page(self, *, limit: int, after_id: int | None = None) -> AssetPage: ...
    def by_public_ids(self, public_ids: tuple[str, ...]) -> AssetPage: ...
    def detail(self, public_id: str) -> AssetDetail | None: ...
    def derivative_path(self, public_id: str, kind: str) -> str | None: ...


class CatalogEditApplicationService(Protocol):
    def update_with_tags(
        self,
        *,
        public_id: str,
        expected_revision: int,
        patch: MetadataPatch,
        tag_names: tuple[str, ...],
    ) -> object: ...
    def update_review_batch(
        self, *, targets: tuple[BatchReviewTarget, ...], patch: ReviewPatch
    ) -> object: ...
    def update_subject_location(
        self,
        *,
        public_id: str,
        latitude: float | None,
        longitude: float | None,
        place_name: str | None,
    ) -> None: ...


class CatalogThumbnailService(Protocol):
    def load(
        self, *, source_path: Path | None, cached_path: Path | None, max_size: int
    ) -> bytes | None: ...


class CatalogMaintenanceApplicationService(Protocol):
    def trash(self, asset_public_id: str) -> bool: ...
    def restore(self, asset_public_id: str) -> bool: ...
    def removal_preview(self, asset_public_id: str) -> object: ...
    def permanently_delete(
        self,
        asset_public_id: str,
        *,
        observation_policy: Literal["block", "unlink", "delete"] = "block",
    ) -> object: ...


class QuickSearchApplicationService(Protocol):
    def page(
        self,
        *,
        text: str = "",
        filters: StructuredAssetFilters | None = None,
        limit: int,
        after_id: int | None = None,
        scope: str = "all",
    ) -> AssetPage: ...


class LibraryViewsApplicationService(Protocol):
    def save_current_search(
        self, *, name: str, text: str, filters: StructuredAssetFilters
    ) -> object: ...
    def list_saved_searches(self) -> tuple[object, ...]: ...
    def delete_saved_search(self, public_id: str) -> None: ...
    def page_saved_search(
        self, *, public_id: str, limit: int, after_id: int | None = None
    ) -> AssetPage: ...
    def create_manual_collection(self, *, name: str, description: str | None = None) -> None: ...
    def create_smart_collection(
        self,
        *,
        name: str,
        text: str,
        filters: StructuredAssetFilters,
        description: str | None = None,
    ) -> None: ...
    def add_assets_to_collection(
        self, *, collection_public_id: str, asset_public_ids: tuple[str, ...]
    ) -> None: ...
    def remove_assets_from_collection(
        self, *, collection_public_id: str, asset_public_ids: tuple[str, ...]
    ) -> None: ...
    def update_collection(
        self, *, public_id: str, name: str, description: str | None = None
    ) -> None: ...
    def delete_collection(self, public_id: str) -> None: ...
    def list_collections(self) -> tuple[object, ...]: ...
    def page_collection(
        self, *, public_id: str, limit: int, after_id: int | None = None
    ) -> AssetPage: ...


class _GalleryModel(QAbstractListModel):
    PublicIdRole = int(Qt.ItemDataRole.UserRole)
    RevisionRole = PublicIdRole + 1
    SourcePathRole = PublicIdRole + 2
    CachedPathRole = PublicIdRole + 3

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[object] = []
        self._icons: dict[str, QIcon] = {}
        self._status: dict[str, str] = {}
        self._row_by_id: dict[str, int] = {}
        self._placeholder = QIcon()

    def set_placeholder(self, icon: QIcon) -> None:
        self._placeholder = icon

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        public_id = str(row.public_id)
        if role == int(Qt.ItemDataRole.DisplayRole):
            return row.title or (Path(row.primary_path).name if row.primary_path else public_id)
        if role == int(Qt.ItemDataRole.DecorationRole):
            return self._icons.get(public_id, self._placeholder)
        if role == int(Qt.ItemDataRole.ToolTipRole):
            return row.primary_path or public_id
        if role == int(Qt.ItemDataRole.StatusTipRole):
            return self._status.get(public_id, "Thumbnail queued")
        if role == self.PublicIdRole:
            return public_id
        if role == self.RevisionRole:
            return int(row.revision)
        if role == self.SourcePathRole:
            return row.primary_path
        if role == self.CachedPathRole:
            return row.thumbnail_path
        return None

    def clear(self) -> None:
        if not self._rows:
            return
        self.beginResetModel()
        self._rows.clear()
        self._icons.clear()
        self._status.clear()
        self._row_by_id.clear()
        self.endResetModel()

    def append_rows(self, rows: tuple[object, ...]) -> None:
        if not rows:
            return
        start = len(self._rows)
        self.beginInsertRows(QModelIndex(), start, start + len(rows) - 1)
        self._rows.extend(rows)
        for offset, row in enumerate(rows):
            self._row_by_id[str(row.public_id)] = start + offset
        self.endInsertRows()

    def remove_public_ids(self, public_ids: set[str]) -> tuple[str, ...]:
        """Remove only matching rows without resetting the model or scroll state."""
        rows = [
            row_index
            for row_index, row in enumerate(self._rows)
            if str(row.public_id) in public_ids
        ]
        if not rows:
            return ()
        removed: list[str] = []
        ranges: list[tuple[int, int]] = []
        start = previous = rows[0]
        for row_index in rows[1:]:
            if row_index == previous + 1:
                previous = row_index
                continue
            ranges.append((start, previous))
            start = previous = row_index
        ranges.append((start, previous))
        for start, end in reversed(ranges):
            self.beginRemoveRows(QModelIndex(), start, end)
            removed.extend(str(row.public_id) for row in self._rows[start : end + 1])
            del self._rows[start : end + 1]
            self.endRemoveRows()
        for public_id in removed:
            self._icons.pop(public_id, None)
            self._status.pop(public_id, None)
        self._row_by_id = {str(row.public_id): index for index, row in enumerate(self._rows)}
        return tuple(removed)

    def index_for_public_id(self, public_id: str) -> QModelIndex:
        row = self._row_by_id.get(public_id)
        return QModelIndex() if row is None else self.index(row, 0)

    def public_ids(self) -> tuple[str, ...]:
        return tuple(str(row.public_id) for row in self._rows)

    def set_thumbnail(self, public_id: str, icon: QIcon | None, status: str) -> None:
        row = self._row_by_id.get(public_id)
        if row is None:
            return
        if icon is not None:
            self._icons[public_id] = icon
        self._status[public_id] = status
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [int(Qt.ItemDataRole.DecorationRole), int(Qt.ItemDataRole.StatusTipRole)])


class _GalleryDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(220, 240)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        painter.save()
        self.initStyleOption(option, index)
        option.decorationSize = QSize(192, 192)
        option.displayAlignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        option.decorationAlignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        option.textElideMode = Qt.TextElideMode.ElideMiddle
        style = option.widget.style() if option.widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)
        painter.restore()


class _CatalogWorker(QObject):
    page_ready = Signal(object, bool, int)
    failed = Signal(str, int)

    def __init__(
        self,
        service: CatalogApplicationService,
        search: QuickSearchApplicationService,
        views: LibraryViewsApplicationService,
        *,
        search_text: str,
        filters: StructuredAssetFilters,
        after_id: int | None,
        append: bool,
        request_id: int,
        view_kind: str | None = None,
        view_public_id: str | None = None,
        import_public_ids: tuple[str, ...] = (),
        search_scope: str = "all",
    ) -> None:
        super().__init__()
        self._service = service
        self._search = search
        self._views = views
        self._search_text = search_text
        self._filters = filters
        self._after_id = after_id
        self._append = append
        self._request_id = request_id
        self._view_kind = view_kind
        self._view_public_id = view_public_id
        self._import_public_ids = import_public_ids
        self._search_scope = search_scope

    @Slot()
    def run(self) -> None:
        try:
            if self._import_public_ids:
                page = self._service.by_public_ids(self._import_public_ids)
            elif self._view_kind == "saved" and self._view_public_id:
                page = self._views.page_saved_search(
                    public_id=self._view_public_id, limit=120, after_id=self._after_id
                )
            elif self._view_kind == "collection" and self._view_public_id:
                page = self._views.page_collection(
                    public_id=self._view_public_id, limit=120, after_id=self._after_id
                )
            elif self._search_text or not self._filters.is_empty():
                page = self._search.page(
                    text=self._search_text,
                    filters=self._filters,
                    limit=120,
                    after_id=self._after_id,
                    scope=self._search_scope,
                )
            else:
                page = self._service.page(limit=120, after_id=self._after_id)
            self.page_ready.emit(page, self._append, self._request_id)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}", self._request_id)


class _ViewsWorker(QObject):
    loaded = Signal(object, object)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(
        self, service: LibraryViewsApplicationService, operation: str, **kwargs: object
    ) -> None:
        super().__init__()
        self._service = service
        self._operation = operation
        self._kwargs = kwargs

    @Slot()
    def run(self) -> None:
        try:
            if self._operation == "load":
                self.loaded.emit(
                    self._service.list_saved_searches(), self._service.list_collections()
                )
            elif self._operation == "save_search":
                self._service.save_current_search(**self._kwargs)
                self.completed.emit("Saved search created")
            elif self._operation == "delete_search":
                self._service.delete_saved_search(str(self._kwargs["public_id"]))
                self.completed.emit("Saved search deleted")
            elif self._operation == "create_collection":
                self._service.create_manual_collection(**self._kwargs)
                self.completed.emit("Collection created")
            elif self._operation == "create_smart_collection":
                self._service.create_smart_collection(**self._kwargs)
                self.completed.emit("Smart collection created")
            elif self._operation == "add_assets":
                self._service.add_assets_to_collection(**self._kwargs)
                self.completed.emit("Assets added to collection")
            elif self._operation == "remove_assets":
                self._service.remove_assets_from_collection(**self._kwargs)
                self.completed.emit("Assets removed from collection")
            elif self._operation == "update_collection":
                self._service.update_collection(**self._kwargs)
                self.completed.emit("Collection updated")
            elif self._operation == "delete_collection":
                self._service.delete_collection(str(self._kwargs["public_id"]))
                self.completed.emit("Collection deleted")
            else:
                raise ValueError(f"unsupported views operation: {self._operation}")
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _MaintenanceWorker(QObject):
    completed = Signal(str, object)
    failed = Signal(str)

    def __init__(
        self,
        service: CatalogMaintenanceApplicationService,
        operation: str,
        asset_public_ids: tuple[str, ...],
        *,
        observation_policy: Literal["block", "unlink", "delete"] = "block",
    ) -> None:
        super().__init__()
        self._service = service
        self._operation = operation
        self._asset_public_ids = asset_public_ids
        self._observation_policy = observation_policy

    @Slot()
    def run(self) -> None:
        try:
            if self._operation == "trash":
                changed = sum(
                    1 for public_id in self._asset_public_ids if self._service.trash(public_id)
                )
                self.completed.emit("trash", changed)
                return
            if self._operation == "delete":
                results = tuple(
                    self._service.permanently_delete(
                        public_id, observation_policy=self._observation_policy
                    )
                    for public_id in self._asset_public_ids
                )
                self.completed.emit("delete", results)
                return
            raise ValueError(f"unsupported maintenance operation: {self._operation}")
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _DetailWorker(QObject):
    ready = Signal(str, object)
    failed = Signal(str)

    def __init__(self, service: CatalogApplicationService, public_id: str) -> None:
        super().__init__()
        self._service = service
        self._public_id = public_id

    @Slot()
    def run(self) -> None:
        try:
            self.ready.emit(self._public_id, self._service.detail(self._public_id))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _PreviewWorker(QObject):
    ready = Signal(int, object)

    def __init__(
        self,
        service: CatalogThumbnailService,
        *,
        request_id: int,
        source: Path | None,
        cached: Path | None,
    ) -> None:
        super().__init__()
        self._service = service
        self._request_id = request_id
        self._source = source
        self._cached = cached

    @Slot()
    def run(self) -> None:
        try:
            data = self._service.load(
                source_path=self._source, cached_path=self._cached, max_size=900
            )
        except Exception:
            data = None
        self.ready.emit(self._request_id, data)


class _ThumbnailWorker(QObject):
    ready = Signal(str, object)

    def __init__(
        self,
        service: CatalogThumbnailService,
        catalog: CatalogApplicationService,
        public_id: str,
        source: Path | None,
        cached: Path | None,
    ) -> None:
        super().__init__()
        self._service = service
        self._catalog = catalog
        self._public_id = public_id
        self._source = source
        self._cached = cached

    @Slot()
    def run(self) -> None:
        try:
            cached = self._cached
            if cached is None or not cached.is_absolute():
                current = self._catalog.derivative_path(self._public_id, "thumbnail")
                if current:
                    cached = Path(current)
            if cached is None:
                stable_path = getattr(self._service, "asset_cache_path", None)
                if callable(stable_path):
                    cached = stable_path(self._public_id)
            data = self._service.load(
                # Gallery workers are cache readers only. Original decoding and
                # derivative writes belong to the durable background JobEngine.
                source_path=None, cached_path=cached, max_size=192
            )
        except Exception:
            data = None
        self.ready.emit(self._public_id, data)


class _MetadataSaveWorker(QObject):
    saved = Signal(str)
    failed = Signal(str, str)

    def __init__(
        self,
        service: CatalogEditApplicationService,
        *,
        public_id: str,
        expected_revision: int,
        patch: MetadataPatch,
        tag_names: tuple[str, ...],
        subject_latitude: float | None,
        subject_longitude: float | None,
        subject_place_name: str | None,
    ) -> None:
        super().__init__()
        self._service = service
        self._public_id = public_id
        self._expected_revision = expected_revision
        self._patch = patch
        self._tag_names = tag_names
        self._subject_latitude = subject_latitude
        self._subject_longitude = subject_longitude
        self._subject_place_name = subject_place_name

    @Slot()
    def run(self) -> None:
        try:
            self._service.update_with_tags(
                public_id=self._public_id,
                expected_revision=self._expected_revision,
                patch=self._patch,
                tag_names=self._tag_names,
            )
            self._service.update_subject_location(
                public_id=self._public_id,
                latitude=self._subject_latitude,
                longitude=self._subject_longitude,
                place_name=self._subject_place_name,
            )
        except Exception as exc:
            self.failed.emit(self._public_id, f"{type(exc).__name__}: {exc}")
            return
        self.saved.emit(self._public_id)


class _BatchReviewWorker(QObject):
    saved = Signal(int)
    failed = Signal(str)

    def __init__(
        self,
        catalog: CatalogApplicationService,
        service: CatalogEditApplicationService,
        *,
        targets: tuple[BatchReviewTarget, ...],
        changes: dict[str, object],
    ) -> None:
        super().__init__()
        self._catalog = catalog
        self._service = service
        self._targets = targets
        self._changes = changes

    @Slot()
    def run(self) -> None:
        count = 0
        try:
            for target in self._targets:
                detail = self._catalog.detail(target.public_id)
                if detail is None:
                    continue
                patch = MetadataPatch(
                    title=self._changes.get("title", detail.title),
                    caption=self._changes.get("caption", detail.caption),
                    user_notes=self._changes.get("user_notes", detail.user_notes),
                    rating=self._changes.get("rating", detail.rating),
                    color_label=self._changes.get("color_label", detail.color_label),
                    pick_state=self._changes.get("pick_state", detail.pick_state),
                )
                tags = self._changes.get("tags", detail.tags)
                self._service.update_with_tags(
                    public_id=target.public_id,
                    expected_revision=target.expected_revision,
                    patch=patch,
                    tag_names=tuple(tags),
                )
                if any(k in self._changes for k in ("subject_latitude", "subject_longitude", "subject_place_name")):
                    self._service.update_subject_location(
                        public_id=target.public_id,
                        latitude=self._changes.get("subject_latitude", detail.subject_latitude),
                        longitude=self._changes.get("subject_longitude", detail.subject_longitude),
                        place_name=self._changes.get("subject_place_name", detail.subject_place_name),
                    )
                count += 1
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.saved.emit(count)


class LibraryWorkspace(QWidget):
    """Paged, non-blocking catalog browser with viewer launch integration."""

    viewer_requested = Signal(object, str)

    def __init__(
        self,
        catalog: CatalogApplicationService,
        thumbnails: CatalogThumbnailService,
        editor: CatalogEditApplicationService,
        search: QuickSearchApplicationService,
        views: LibraryViewsApplicationService,
        maintenance: CatalogMaintenanceApplicationService | None = None,
        parent: QWidget | None = None,
        *,
        workspace_mode: str = "library",
        enrichment_controller: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._catalog = catalog
        self._thumbnails = thumbnails
        self._editor = editor
        self._search_service = search
        self._views_service = views
        self._maintenance_service = maintenance
        self._workspace_mode = workspace_mode
        self._enrichment_panel = None
        self._enrichment_controller = enrichment_controller
        self._capability_run = None
        self._capability_progress: QProgressDialog | None = None
        self._batch_screen = None
        self._batch_screens: list[object] = []
        self._workspace_enabled = True
        self._capability_timer = QTimer(self)
        self._capability_timer.setInterval(100)
        self._capability_timer.timeout.connect(self._poll_photo_capability)
        self._search_text = ""
        self._search_scope_value = "all"
        self._active_view_kind: str | None = None
        self._active_view_id: str | None = None
        self._active_view_name: str | None = None
        self._active_filters = StructuredAssetFilters()
        self._page_request_id = 0
        self._next_cursor: int | None = None
        self._threads: set[QThread] = set()
        self._workers: set[QObject] = set()
        self._thumbnail_inputs: dict[str, tuple[Path | None, Path | None]] = {}
        self._failed_thumbnails: set[str] = set()
        self._thumbnail_queue: deque[tuple[str, Path | None, Path | None]] = deque()
        self._thumbnail_queued: set[str] = set()
        self._thumbnail_inflight: set[str] = set()
        self._thumbnail_loaded: set[str] = set()
        self._thumbnail_active = 0
        # Thumbnail files are already durable cache artifacts. Keep GUI reads
        # strictly serial and maintain only a small viewport-local queue so a
        # large library cannot flood Windows with short-lived read threads.
        self._thumbnail_limit = 1
        self._thumbnail_queue_limit = 12
        self._thumbnail_poll_timer = QTimer(self)
        self._thumbnail_poll_timer.setInterval(10000)
        self._thumbnail_poll_timer.timeout.connect(self._poll_pending_thumbnails)
        self._thumbnail_poll_timer.start()
        self._scrolling = False
        self._last_scroll_value = 0
        self._scroll_direction = 1
        self._scroll_idle_timer = QTimer(self)
        self._scroll_idle_timer.setSingleShot(True)
        self._scroll_idle_timer.setInterval(300)
        self._scroll_idle_timer.timeout.connect(self._scrolling_stopped)
        self._preview_request_id = 0
        self._selected_public_id: str | None = None
        self._detail: AssetDetail | None = None
        self._loading_editor = False
        self._metadata_dirty = False
        self._selection_guard = False
        self._import_public_ids: tuple[str, ...] = ()
        self._pending_import_sync: dict[str, object] | None = None
        self._refreshing = False
        self._pending_maintenance_ids: tuple[str, ...] = ()
        self._active = False

        self._count = QLabel("0 assets")
        self._thumbnail_status = QLabel("Thumbnails idle")
        self._thumbnail_status.setAccessibleName("Background thumbnail queue status")
        self._view_selector = QComboBox()
        self._view_selector.addItem(
            "All Photos" if workspace_mode == "library" else "All Library", "library"
        )
        self._view_selector.setAccessibleName("Library view")
        self._view_selector.currentIndexChanged.connect(self._view_selection_changed)
        self._refresh = QPushButton("Refresh")
        self._refresh.clicked.connect(self.refresh)
        self._more = QPushButton("Load more")
        self._more.clicked.connect(self.load_more)
        self._more.setEnabled(False)
        self._retry_thumbnails = QPushButton("Retry thumbnails")
        self._retry_thumbnails.setEnabled(False)
        self._retry_thumbnails.clicked.connect(self.retry_failed_thumbnails)
        self._open_viewer = QPushButton("Viewer")
        self._open_viewer.setEnabled(False)
        self._open_viewer.clicked.connect(self.open_selected_viewer)
        self._run_capability = QPushButton("Run enrichment…")
        self._run_capability.setEnabled(False)
        self._run_capability.setVisible(
            enrichment_controller is not None and workspace_mode == "library"
        )
        self._run_capability.clicked.connect(self._run_photo_capability)
        self._trash_selected = QPushButton("Trash")
        self._trash_selected.setEnabled(False)
        self._trash_selected.clicked.connect(self.trash_selected_assets)
        if maintenance is None:
            self._trash_selected.hide()
        header = QHBoxLayout()
        header.addWidget(self._count)
        header.addWidget(QLabel("View"))
        header.addWidget(self._view_selector)
        header.addStretch(1)
        header.addWidget(self._refresh)
        header.addWidget(self._retry_thumbnails)
        header.addWidget(self._trash_selected)
        header.addWidget(self._open_viewer)
        header.addWidget(self._more)

        self._search_scope = QComboBox()
        self._search_scope.setAccessibleName("Search in")
        for label, value in (
            ("Everywhere", "all"),
            ("Filename", "filename"),
            ("Title", "title"),
            ("Caption", "caption"),
            ("Notes", "notes"),
            ("Tags", "tags"),
        ):
            self._search_scope.addItem(label, value)
        self._search_scope.currentIndexChanged.connect(lambda _index: self._apply_search())
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Type to search…")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.returnPressed.connect(self._apply_search)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(450)
        self._search_timer.timeout.connect(self._apply_search)
        self._search_input.textChanged.connect(lambda _text: self._search_timer.start())
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Quick search"))
        search_row.addWidget(self._search_input, 1)

        self._minimum_rating = QComboBox()
        self._minimum_rating.addItem("Any", None)
        for rating in range(1, 6):
            self._minimum_rating.addItem(f"{rating}+", rating)
        self._filter_color = QComboBox()
        self._filter_color.addItem("Any", None)
        for value in ("red", "yellow", "green", "blue", "purple"):
            self._filter_color.addItem(value.title(), value)
        self._filter_pick = QComboBox()
        self._filter_pick.addItem("Any", None)
        self._filter_pick.addItem("Pick", "pick")
        self._filter_pick.addItem("Reject", "reject")
        self._date_from_enabled = QCheckBox("From")
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        self._date_from.setEnabled(False)
        self._date_to_enabled = QCheckBox("To")
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("yyyy-MM-dd")
        self._date_to.setEnabled(False)
        self._date_from_enabled.toggled.connect(self._date_from.setEnabled)
        self._date_to_enabled.toggled.connect(self._date_to.setEnabled)
        self._minimum_width = QSpinBox()
        self._minimum_width.setRange(0, 100000)
        self._minimum_width.setSpecialValueText("Any")
        self._minimum_width.setSuffix(" px")
        self._minimum_height = QSpinBox()
        self._minimum_height.setRange(0, 100000)
        self._minimum_height.setSpecialValueText("Any")
        self._minimum_height.setSuffix(" px")
        self._filter_tag = QLineEdit()
        self._filter_tag.setPlaceholderText("Exact tag")
        self._filter_taxonomy = QLineEdit()
        self._filter_taxonomy.setPlaceholderText("Scientific or common name")
        self._filter_camera_make = QLineEdit()
        self._filter_camera_make.setPlaceholderText("Camera maker")
        self._filter_camera_model = QLineEdit()
        self._filter_camera_model.setPlaceholderText("Camera model")
        self._filter_lens = QLineEdit()
        self._filter_lens.setPlaceholderText("Lens")
        self._gps_bounds_enabled = QCheckBox("GPS bounds")
        self._exact_duplicates_only = QCheckBox("Exact duplicates only")
        self._exact_duplicates_only.setToolTip(
            "Show assets with two or more available files sharing the same SHA-256 checksum"
        )
        self._gps_south = QDoubleSpinBox()
        self._gps_north = QDoubleSpinBox()
        self._gps_west = QDoubleSpinBox()
        self._gps_east = QDoubleSpinBox()
        for control, minimum, maximum in (
            (self._gps_south, -90.0, 90.0),
            (self._gps_north, -90.0, 90.0),
            (self._gps_west, -180.0, 180.0),
            (self._gps_east, -180.0, 180.0),
        ):
            control.setRange(minimum, maximum)
            control.setDecimals(5)
            control.setEnabled(False)
        self._gps_south.setValue(-90.0)
        self._gps_north.setValue(90.0)
        self._gps_west.setValue(-180.0)
        self._gps_east.setValue(180.0)
        for control in (self._gps_south, self._gps_north, self._gps_west, self._gps_east):
            self._gps_bounds_enabled.toggled.connect(control.setEnabled)
        self._clear_filters = QPushButton("Clear filters")
        self._clear_filters.clicked.connect(self.clear_filters)

        filters_box = QGroupBox("Structured filters")
        filters_layout = QGridLayout(filters_box)
        filters_layout.setContentsMargins(12, 18, 12, 12)
        filters_layout.setHorizontalSpacing(8)
        filters_layout.setVerticalSpacing(8)

        # A two-control layout remains usable in a narrow persistent sidebar.
        # The previous eight-column grid silently clipped controls on common
        # 1366/1600/1920-wide Windows displays.
        filters_layout.addWidget(QLabel("Rating"), 0, 0)
        filters_layout.addWidget(self._minimum_rating, 0, 1)
        filters_layout.addWidget(QLabel("Color"), 1, 0)
        filters_layout.addWidget(self._filter_color, 1, 1)
        filters_layout.addWidget(QLabel("Pick state"), 2, 0)
        filters_layout.addWidget(self._filter_pick, 2, 1)

        filters_layout.addWidget(self._date_from_enabled, 3, 0)
        filters_layout.addWidget(self._date_from, 3, 1)
        filters_layout.addWidget(self._date_to_enabled, 4, 0)
        filters_layout.addWidget(self._date_to, 4, 1)
        filters_layout.addWidget(QLabel("Minimum width"), 5, 0)
        filters_layout.addWidget(self._minimum_width, 5, 1)
        filters_layout.addWidget(QLabel("Minimum height"), 6, 0)
        filters_layout.addWidget(self._minimum_height, 6, 1)

        filters_layout.addWidget(QLabel("Tag"), 7, 0)
        filters_layout.addWidget(self._filter_tag, 7, 1)
        filters_layout.addWidget(QLabel("Taxonomy"), 8, 0)
        filters_layout.addWidget(self._filter_taxonomy, 8, 1)
        filters_layout.addWidget(QLabel("Camera maker"), 9, 0)
        filters_layout.addWidget(self._filter_camera_make, 9, 1)
        filters_layout.addWidget(QLabel("Camera model"), 10, 0)
        filters_layout.addWidget(self._filter_camera_model, 10, 1)
        filters_layout.addWidget(QLabel("Lens"), 11, 0)
        filters_layout.addWidget(self._filter_lens, 11, 1)

        filters_layout.addWidget(self._gps_bounds_enabled, 12, 0, 1, 2)
        filters_layout.addWidget(QLabel("South"), 13, 0)
        filters_layout.addWidget(self._gps_south, 13, 1)
        filters_layout.addWidget(QLabel("North"), 14, 0)
        filters_layout.addWidget(self._gps_north, 14, 1)
        filters_layout.addWidget(QLabel("West"), 15, 0)
        filters_layout.addWidget(self._gps_west, 15, 1)
        filters_layout.addWidget(QLabel("East"), 16, 0)
        filters_layout.addWidget(self._gps_east, 16, 1)
        filters_layout.addWidget(self._exact_duplicates_only, 17, 0, 1, 2)
        filters_layout.addWidget(self._clear_filters, 18, 0, 1, 2)
        filters_layout.setColumnStretch(1, 1)

        for combo in (self._minimum_rating, self._filter_color, self._filter_pick):
            combo.currentIndexChanged.connect(lambda _index: self._search_timer.start())
        for spin in (self._minimum_width, self._minimum_height):
            spin.valueChanged.connect(lambda _value: self._search_timer.start())
        for edit in (
            self._filter_tag,
            self._filter_taxonomy,
            self._filter_camera_make,
            self._filter_camera_model,
            self._filter_lens,
        ):
            edit.textChanged.connect(lambda _text: self._search_timer.start())
            edit.returnPressed.connect(self._apply_search)
        for check in (self._date_from_enabled, self._date_to_enabled):
            check.toggled.connect(lambda _checked: self._search_timer.start())
        self._date_from.dateChanged.connect(lambda _date: self._search_timer.start())
        self._date_to.dateChanged.connect(lambda _date: self._search_timer.start())
        self._gps_bounds_enabled.toggled.connect(lambda _checked: self._search_timer.start())
        self._exact_duplicates_only.toggled.connect(lambda _checked: self._search_timer.start())
        for control in (self._gps_south, self._gps_north, self._gps_west, self._gps_east):
            control.valueChanged.connect(lambda _value: self._search_timer.start())

        self._saved_searches = QComboBox()
        self._saved_searches.addItem("Saved searches…", None)
        self._open_saved_search = QPushButton("Open")
        self._open_saved_search.clicked.connect(self.open_saved_search)
        self._save_search = QPushButton("Save current search…")
        self._save_search.clicked.connect(self.save_current_search)
        self._delete_search = QPushButton("Delete")
        self._delete_search.clicked.connect(self.delete_saved_search)
        self._collection_records: tuple[object, ...] = ()
        self._collections = QComboBox()
        self._collections.addItem("Collections…", None)
        self._open_collection = QPushButton("Open")
        self._open_collection.clicked.connect(self.open_collection)
        self._new_collection = QPushButton("New collection…")
        self._new_collection.clicked.connect(self.create_collection)
        self._new_smart_collection = QPushButton("Save as smart…")
        self._new_smart_collection.clicked.connect(self.create_smart_collection)
        self._edit_collection = QPushButton("Edit…")
        self._edit_collection.clicked.connect(self.edit_collection)
        self._delete_collection = QPushButton("Delete")
        self._delete_collection.clicked.connect(self.delete_collection)
        self._add_to_collection = QPushButton("Add selected to…")
        self._add_to_collection.clicked.connect(self.add_selected_to_collection)
        self._remove_from_collection = QPushButton("Remove selected")
        self._remove_from_collection.clicked.connect(self.remove_selected_from_collection)
        self._active_view = QLabel("")
        self._clear_view = QPushButton("Return to Library")
        self._clear_view.setEnabled(False)
        self._clear_view.clicked.connect(self.clear_active_view)
        views_box = QGroupBox("Collections")
        views_layout = QGridLayout(views_box)
        views_layout.setContentsMargins(12, 18, 12, 12)
        views_layout.setHorizontalSpacing(8)
        views_layout.setVerticalSpacing(8)

        # Controls are deliberately stacked instead of spread across four
        # columns, so every action keeps its full label in the Collections pane.
        views_layout.addWidget(QLabel("Saved searches"), 0, 0, 1, 2)
        views_layout.addWidget(self._saved_searches, 1, 0, 1, 2)
        views_layout.addWidget(self._open_saved_search, 2, 0)
        views_layout.addWidget(self._save_search, 2, 1)
        views_layout.addWidget(self._delete_search, 3, 0, 1, 2)

        views_layout.addWidget(QLabel("Collections"), 4, 0, 1, 2)
        views_layout.addWidget(self._collections, 5, 0, 1, 2)
        views_layout.addWidget(self._open_collection, 6, 0)
        views_layout.addWidget(self._new_collection, 6, 1)
        views_layout.addWidget(self._new_smart_collection, 7, 0, 1, 2)
        views_layout.addWidget(self._edit_collection, 8, 0)
        views_layout.addWidget(self._delete_collection, 8, 1)
        views_layout.addWidget(self._add_to_collection, 9, 0, 1, 2)
        views_layout.addWidget(self._remove_from_collection, 10, 0, 1, 2)
        views_layout.addWidget(self._active_view, 11, 0, 1, 2)
        views_layout.addWidget(self._clear_view, 12, 0, 1, 2)
        views_layout.setColumnStretch(0, 1)
        views_layout.setColumnStretch(1, 1)

        # Collection-manager controls must never impose their label widths on
        # the workspace splitter. This is especially important on the first
        # presentation, before the asynchronous Library/collection load causes
        # Qt to recalculate the layout.
        collection_manager_controls = (
            self._saved_searches,
            self._open_saved_search,
            self._save_search,
            self._delete_search,
            self._collections,
            self._open_collection,
            self._new_collection,
            self._new_smart_collection,
            self._edit_collection,
            self._delete_collection,
            self._add_to_collection,
            self._remove_from_collection,
            self._active_view,
            self._clear_view,
        )
        for control in collection_manager_controls:
            control.setMinimumWidth(0)
            control.setSizePolicy(QSizePolicy.Policy.Ignored, control.sizePolicy().verticalPolicy())
        self._active_view.setWordWrap(True)

        self._last_selected_asset_ids: tuple[str, ...] = ()
        self._gallery_model = _GalleryModel(self)
        self._gallery_model.set_placeholder(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self._grid = QListView()
        self._grid.setModel(self._gallery_model)
        self._grid.setItemDelegate(_GalleryDelegate(self._grid))
        self._grid.setViewMode(QListView.ViewMode.IconMode)
        self._grid.setResizeMode(QListView.ResizeMode.Fixed)
        self._grid.setMovement(QListView.Movement.Static)
        self._grid.setUniformItemSizes(True)
        self._grid.setLayoutMode(QListView.LayoutMode.Batched)
        self._grid.setBatchSize(48)
        self._grid.setIconSize(QSize(192, 192))
        self._grid.setGridSize(QSize(220, 240))
        self._grid.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        self._grid.selectionModel().selectionChanged.connect(lambda *_args: self._selection_changed())
        self._grid.doubleClicked.connect(lambda _index: self.open_selected_viewer())
        gallery_scrollbar = self._grid.verticalScrollBar()
        gallery_scrollbar.valueChanged.connect(self._gallery_scrolled)
        gallery_scrollbar.sliderReleased.connect(self._scrolling_stopped)

        self._preview = QLabel("No selection")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(QSize(0, 180))
        self._preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._preview.setMaximumHeight(280)
        self._preview.setWordWrap(True)
        self._technical = QLabel("")
        self._technical.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._technical.setWordWrap(True)
        self._technical.setMinimumWidth(0)
        self._technical.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self._title = QLineEdit()
        self._caption = QTextEdit()
        self._caption.setMinimumHeight(52)
        self._caption.setMaximumHeight(72)
        self._notes = QTextEdit()
        self._notes.setMinimumHeight(52)
        self._notes.setMaximumHeight(72)
        self._rating = QSpinBox()
        self._rating.setRange(0, 5)
        self._rating.setSpecialValueText("Unrated")
        self._color = QComboBox()
        self._color.addItem("None", None)
        for value in ("red", "yellow", "green", "blue", "purple"):
            self._color.addItem(value.title(), value)
        self._pick = QComboBox()
        self._pick.addItem("None", None)
        self._pick.addItem("Pick", "pick")
        self._pick.addItem("Reject", "reject")
        self._tags = QLineEdit()
        self._tags.setPlaceholderText("Comma-separated tags")
        self._capture_location = QLabel("No embedded GPS location")
        self._capture_location.setWordWrap(True)
        self._subject_name = QLineEdit()
        self._subject_name.setPlaceholderText("e.g. Wolf den, north hide, lake edge")
        self._subject_latitude = QDoubleSpinBox()
        self._subject_latitude.setRange(-90.0, 90.0)
        self._subject_latitude.setDecimals(7)
        self._subject_latitude.setSpecialValueText("Not set")
        self._subject_latitude.setMinimum(-90.0)
        self._subject_longitude = QDoubleSpinBox()
        self._subject_longitude.setRange(-180.0, 180.0)
        self._subject_longitude.setDecimals(7)
        self._subject_longitude.setSpecialValueText("Not set")
        self._subject_longitude.setMinimum(-180.0)

        # No editor may propagate a content-based minimum width into the inspector.
        for control in (
            self._title,
            self._caption,
            self._notes,
            self._rating,
            self._color,
            self._pick,
            self._tags,
            self._subject_name,
            self._subject_latitude,
            self._subject_longitude,
        ):
            control.setMinimumWidth(0)
            control.setSizePolicy(QSizePolicy.Policy.Ignored, control.sizePolicy().verticalPolicy())
        for editor in (self._caption, self._notes):
            editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.addRow("Title", self._title)
        form.addRow("Caption", self._caption)
        form.addRow("Notes", self._notes)
        form.addRow("Rating", self._rating)
        form.addRow("Color", self._color)
        form.addRow("Pick state", self._pick)
        form.addRow("User tags", self._tags)

        location_box = QGroupBox("Geolocation")
        location_form = QFormLayout(location_box)
        location_form.addRow("Capture location", self._capture_location)
        location_form.addRow("Subject location name", self._subject_name)
        location_form.addRow("Subject latitude", self._subject_latitude)
        location_form.addRow("Subject longitude", self._subject_longitude)

        self._batch_title = QLineEdit()
        self._batch_title.setPlaceholderText("No change")
        self._batch_caption = QTextEdit()
        self._batch_caption.setPlaceholderText("No change")
        self._batch_caption.setMaximumHeight(90)
        self._batch_notes = QTextEdit()
        self._batch_notes.setPlaceholderText("No change")
        self._batch_notes.setMaximumHeight(90)
        self._batch_rating = QComboBox()
        self._batch_rating.addItem("No change", "unchanged")
        self._batch_rating.addItem("Unrated", None)
        for rating in range(1, 6):
            self._batch_rating.addItem(str(rating), rating)
        self._batch_color = QComboBox()
        self._batch_color.addItem("No change", "unchanged")
        self._batch_color.addItem("Clear", None)
        for value in ("red", "yellow", "green", "blue", "purple"):
            self._batch_color.addItem(value.title(), value)
        self._batch_pick = QComboBox()
        self._batch_pick.addItem("No change", "unchanged")
        self._batch_pick.addItem("Clear", None)
        self._batch_pick.addItem("Pick", "pick")
        self._batch_pick.addItem("Reject", "reject")
        self._batch_tags = QLineEdit()
        self._batch_tags.setPlaceholderText("No change; enter comma-separated tags")
        self._batch_subject_name = QLineEdit()
        self._batch_subject_name.setPlaceholderText("No change")
        self._batch_subject_latitude = QLineEdit()
        self._batch_subject_latitude.setPlaceholderText("No change")
        self._batch_subject_longitude = QLineEdit()
        self._batch_subject_longitude.setPlaceholderText("No change")
        self._apply_batch_review = QPushButton("Apply to selection")
        self._apply_batch_review.setEnabled(False)
        self._apply_batch_review.clicked.connect(self.apply_batch_review)
        batch_box = QGroupBox("Batch update")
        self._batch_box = batch_box
        batch_layout = QFormLayout(batch_box)
        batch_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        batch_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        batch_layout.addRow("Title", self._batch_title)
        batch_layout.addRow("Caption", self._batch_caption)
        batch_layout.addRow("Notes", self._batch_notes)
        batch_layout.addRow("Rating", self._batch_rating)
        batch_layout.addRow("Color", self._batch_color)
        batch_layout.addRow("Pick state", self._batch_pick)
        batch_layout.addRow("User tags", self._batch_tags)
        batch_location_box = QGroupBox("Geolocation")
        batch_location_form = QFormLayout(batch_location_box)
        batch_location_form.addRow("Subject location name", self._batch_subject_name)
        batch_location_form.addRow("Subject latitude", self._batch_subject_latitude)
        batch_location_form.addRow("Subject longitude", self._batch_subject_longitude)
        batch_layout.addRow(batch_location_box)
        batch_layout.addRow(self._apply_batch_review)

        self._save_metadata = QPushButton("Save")
        self._save_metadata.setEnabled(False)
        self._save_metadata.clicked.connect(self.save_metadata)
        self._discard_metadata = QPushButton("Discard")
        self._discard_metadata.setEnabled(False)
        self._discard_metadata.clicked.connect(self.discard_metadata)
        metadata_buttons = QHBoxLayout()
        metadata_buttons.addWidget(self._save_metadata)
        metadata_buttons.addWidget(self._discard_metadata)
        metadata_buttons.addStretch(1)

        for control in (self._title, self._tags, self._subject_name):
            control.textChanged.connect(self._mark_metadata_dirty)
        for control in (self._caption, self._notes):
            control.textChanged.connect(self._mark_metadata_dirty)
        self._rating.valueChanged.connect(self._mark_metadata_dirty)
        self._color.currentIndexChanged.connect(self._mark_metadata_dirty)
        self._pick.currentIndexChanged.connect(self._mark_metadata_dirty)
        self._subject_latitude.valueChanged.connect(self._mark_metadata_dirty)
        self._subject_longitude.valueChanged.connect(self._mark_metadata_dirty)
        self._save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self._save_shortcut.activated.connect(self.save_metadata)
        self._discard_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._discard_shortcut.activated.connect(self.discard_metadata)

        right = QWidget()
        right.setMinimumWidth(0)
        right.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self._technical)
        self._photo_box = QGroupBox("Photo")
        photo_layout = QVBoxLayout(self._photo_box)
        photo_layout.addLayout(form)
        photo_layout.addWidget(location_box)
        photo_layout.addLayout(metadata_buttons)
        right_layout.addWidget(self._photo_box)
        right_layout.addWidget(batch_box)

        # Contextual Library workspace: the photographic grid owns the canvas.
        # Refine, Organize, and Inspector are revealed only for the active task.
        self.setObjectName("libraryWorkspace")
        self._grid.setObjectName("libraryGrid")
        right.setObjectName("libraryInspector")
        filters_box.setObjectName("libraryPanel")
        views_box.setObjectName("libraryPanel")
        batch_box.setObjectName("libraryPanel")

        self._refine_button = QPushButton("Refine")
        self._refine_button.setCheckable(True)
        self._refine_button.setToolTip("Show or hide filters")
        self._organize_button = QPushButton("Create collection")
        self._organize_button.setCheckable(True)
        self._organize_button.setToolTip("Open collection tools")
        self._inspector_button = QPushButton("Inspector")
        self._inspector_button.setCheckable(True)
        self._inspector_button.setToolTip("Show metadata for the current selection")

        command_bar = QFrame()
        command_bar.setObjectName("libraryCommandBar")
        command_layout = QHBoxLayout(command_bar)
        command_layout.setContentsMargins(12, 8, 12, 8)
        command_layout.setSpacing(8)
        library_label = QLabel("Photos" if self._workspace_mode == "library" else "Collections")
        library_label.setObjectName("libraryTitle")
        command_layout.addWidget(library_label)
        command_layout.addWidget(self._view_selector)
        command_layout.addWidget(QLabel("Search in"))
        command_layout.addWidget(self._search_scope)
        command_layout.addWidget(self._search_input, 1)
        command_layout.addWidget(self._refresh)

        selection_bar = QFrame()
        selection_bar.setObjectName("librarySelectionBar")
        selection_layout = QHBoxLayout(selection_bar)
        selection_layout.setContentsMargins(10, 6, 10, 6)
        selection_layout.setSpacing(8)
        selection_layout.addWidget(self._count)
        selection_layout.addWidget(self._thumbnail_status)
        selection_layout.addStretch(1)
        selection_layout.addWidget(self._retry_thumbnails)
        selection_layout.addWidget(self._trash_selected)
        selection_layout.addWidget(self._run_capability)
        selection_layout.addWidget(self._open_viewer)
        selection_layout.addWidget(self._more)

        refine_drawer = QScrollArea()
        refine_drawer.setObjectName("libraryDrawer")
        refine_drawer.setWidgetResizable(True)
        refine_drawer.setFrameShape(QFrame.Shape.NoFrame)
        refine_drawer.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        refine_drawer.setWidget(filters_box)
        refine_drawer.setMinimumWidth(330)
        refine_drawer.setMaximumWidth(430)

        organize_drawer = QScrollArea()
        organize_drawer.setObjectName("libraryDrawer")
        organize_drawer.setWidgetResizable(True)
        organize_drawer.setFrameShape(QFrame.Shape.NoFrame)
        organize_drawer.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        organize_drawer.setWidget(views_box)
        organize_drawer.setMinimumWidth(240)
        organize_drawer.setMaximumWidth(380)
        organize_drawer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self._refine_drawer = refine_drawer
        self._organize_drawer = organize_drawer
        inspector_scroll = QScrollArea()
        inspector_scroll.setObjectName("libraryInspectorScroll")
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        inspector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inspector_scroll.setWidget(right)
        inspector_scroll.setMinimumWidth(260)
        inspector_scroll.setMaximumWidth(410)
        inspector_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._inspector_panel = inspector_scroll

        # Library and Collections are separate workspaces. Library keeps filters
        # and inline metadata editing visible; Collections owns collection creation
        # and membership tools.
        self._refine_button.hide()
        self._organize_button.hide()
        self._inspector_button.hide()
        if self._workspace_mode == "collections":
            refine_drawer.hide()
            organize_drawer.show()
            self._view_selector.hide()
            library_label.setText("Collections")
        else:
            refine_drawer.show()
            organize_drawer.hide()
            # Collection administration belongs exclusively to Collections.
            for control in (
                self._collections,
                self._open_collection,
                self._new_collection,
                self._new_smart_collection,
                self._edit_collection,
                self._delete_collection,
                self._add_to_collection,
                self._remove_from_collection,
            ):
                control.hide()

        inspector_scroll.show()
        workspace_splitter = QSplitter()
        workspace_splitter.setObjectName(
            "collectionsMainSplitter"
            if self._workspace_mode == "collections"
            else "libraryMainSplitter"
        )
        workspace_splitter.addWidget(
            refine_drawer if self._workspace_mode != "collections" else organize_drawer
        )
        workspace_splitter.addWidget(self._grid)
        workspace_splitter.addWidget(inspector_scroll)
        workspace_splitter.setStretchFactor(0, 0)
        workspace_splitter.setStretchFactor(1, 1)
        workspace_splitter.setStretchFactor(2, 0)
        workspace_splitter.setChildrenCollapsible(False)
        workspace_splitter.setSizes(
            [
                330 if self._workspace_mode == "collections" else 300,
                980,
                380 if self._workspace_mode == "collections" else 360,
            ]
        )
        self._workspace_splitter = workspace_splitter
        self._splitter_settings_key = (
            "ui/collections/main_splitter"
            if self._workspace_mode == "collections"
            else "ui/library/main_splitter"
        )
        workspace_splitter.splitterMoved.connect(lambda _pos, _index: self._save_splitter_state())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)
        layout.addWidget(command_bar)
        if enrichment_controller is not None and self._workspace_mode == "library":
            from natureai_next.domain.enrichment import SubjectRef, SubjectType
            from natureai_next.ui.qt.enrichment import CanonicalEnrichmentPanel

            self._enrichment_panel = CanonicalEnrichmentPanel(
                enrichment_controller,
                SubjectRef(SubjectType.PHOTO, "__none__"),
                self,
                collapsible=True,
                collapse_settings_key="ui/library/photos/enrichment_collapsed",
            )
            subject_splitter = QSplitter(Qt.Orientation.Vertical)
            subject_splitter.addWidget(workspace_splitter)
            subject_splitter.addWidget(self._enrichment_panel)
            subject_splitter.setStretchFactor(0, 4)
            subject_splitter.setStretchFactor(1, 2)
            layout.addWidget(subject_splitter, 1)
        else:
            layout.addWidget(workspace_splitter, 1)
        layout.addWidget(selection_bar)

        self.setStyleSheet("""
            QWidget#libraryWorkspace { background: #101412; }
            QFrame#libraryCommandBar, QFrame#librarySelectionBar {
                background: #171d1a; border: 1px solid #28312c; border-radius: 9px;
            }
            QLabel#libraryTitle { color: #f2f5f3; font-size: 18px; font-weight: 650; padding-right: 8px; }
            QGroupBox#libraryPanel {
                background: #171d1a; border: 1px solid #28312c; border-radius: 9px;
                margin-top: 12px; padding: 12px 10px 10px 10px; font-weight: 600;
            }
            QGroupBox#libraryPanel::title {
                subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #dce5df;
            }
            QListView#libraryGrid {
                background: #0d110f; border: 1px solid #28312c; border-radius: 10px;
                padding: 10px; outline: 0;
            }
            QListView#libraryGrid::item { border-radius: 8px; padding: 5px; color: #dce5df; }
            QListView#libraryGrid::item:hover { background: #202923; }
            QListView#libraryGrid::item:selected { background: #31483b; border: 1px solid #5d8b70; }
            QLabel#libraryPreview {
                background: #0d110f; border: 1px solid #28312c; border-radius: 10px; color: #98a49e;
            }
            QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {
                background: #0f1411; border: 1px solid #344038; border-radius: 6px;
                padding: 6px; color: #edf2ef; selection-background-color: #446650;
            }
            QPushButton {
                background: #26332b; border: 1px solid #3b4b41; border-radius: 6px;
                padding: 7px 10px; color: #edf2ef;
            }
            QPushButton:hover { background: #314238; }
            QPushButton:checked { background: #3b5b48; border-color: #6b9b7c; }
            QPushButton:pressed { background: #1e2a23; }
            QPushButton:disabled { color: #657068; background: #1a201c; border-color: #252d28; }
            QSplitter::handle { background: transparent; width: 5px; height: 5px; }
            QScrollArea#libraryDrawer, QScrollArea#libraryInspectorScroll { background: transparent; }
            QScrollArea#libraryInspectorScroll > QWidget > QWidget { background: #101412; }
            QGroupBox#libraryPanel QLabel { font-weight: 400; }
        """)
        self._restore_splitter_state()
        self.refresh_views()
        if self._workspace_mode == "collections":
            QTimer.singleShot(0, self._constrain_splitter_to_viewport)
            QTimer.singleShot(0, self.focus_collections)
        else:
            self.refresh()

    def activate(self) -> None:
        """Activate without rebuilding the workspace or forcing a full reload."""
        self._active = True
        if self._workspace_mode == "collections":
            self.refresh_views()
        else:
            QTimer.singleShot(0, self._schedule_visible_thumbnails)

    def deactivate(self) -> None:
        self._active = False
        self._thumbnail_queue.clear()
        self._thumbnail_queued.clear()
        self._update_thumbnail_status()
        self._save_splitter_state()

    def refresh_if_stale(self) -> None:
        if self._gallery_model.rowCount() == 0 and self._workspace_mode != "collections":
            self.refresh()

    def _save_splitter_state(self) -> None:
        if not hasattr(self, "_workspace_splitter"):
            return
        QSettings().setValue(self._splitter_settings_key, self._workspace_splitter.saveState())

    def _restore_splitter_state(self) -> None:
        state = QSettings().value(self._splitter_settings_key)
        if not isinstance(state, QByteArray) or state.isEmpty():
            return
        if not self._workspace_splitter.restoreState(state):
            return
        sizes = self._workspace_splitter.sizes()
        if len(sizes) != 3 or any(size <= 0 for size in sizes):
            self._workspace_splitter.setSizes(
                [
                    330 if self._workspace_mode == "collections" else 300,
                    980,
                    380 if self._workspace_mode == "collections" else 360,
                ]
            )

    def _constrain_splitter_to_viewport(self) -> None:
        """Apply one bounded correction after the workspace has a real width.

        Saved geometry can come from a larger monitor, and the initial splitter
        sizes are assigned before the stacked page is laid out.  Collections
        previously appeared out of bounds until an asynchronous Library load
        happened to trigger another layout pass.
        """
        if not hasattr(self, "_workspace_splitter"):
            return
        available = self._workspace_splitter.width()
        if available <= 0:
            return
        handle_space = self._workspace_splitter.handleWidth() * 2
        usable = max(0, available - handle_space)
        if self._workspace_mode == "collections":
            left = min(340, max(240, int(usable * 0.26)))
            right = min(390, max(260, int(usable * 0.30)))
        else:
            left = min(330, max(260, int(usable * 0.24)))
            right = min(380, max(260, int(usable * 0.28)))
        centre = usable - left - right
        minimum_centre = 180
        if centre < minimum_centre:
            deficit = minimum_centre - centre
            left_reduction = min(deficit, max(0, left - 240))
            left -= left_reduction
            deficit -= left_reduction
            right -= min(deficit, max(0, right - 240))
            centre = max(minimum_centre, usable - left - right)
        self._workspace_splitter.setSizes([left, centre, right])

    def showEvent(self, event: object) -> None:
        super().showEvent(event)
        if self._workspace_mode == "collections":
            QTimer.singleShot(0, self._constrain_splitter_to_viewport)

    def closeEvent(self, event: object) -> None:
        self._save_splitter_state()
        super().closeEvent(event)

    @Slot(bool)
    def _toggle_refine_drawer(self, visible: bool) -> None:
        if visible and self._organize_button.isChecked():
            self._organize_button.setChecked(False)
        self._refine_drawer.setVisible(visible)

    @Slot(bool)
    def _toggle_organize_drawer(self, visible: bool) -> None:
        if visible and self._refine_button.isChecked():
            self._refine_button.setChecked(False)
        self._organize_drawer.setVisible(visible)

    @Slot()
    def _apply_search(self) -> None:
        text = " ".join(self._search_input.text().split())
        filters = self._current_filters()
        scope = str(self._search_scope.currentData() or "all")
        if (
            text == self._search_text
            and scope == self._search_scope_value
            and filters == self._active_filters
            and self._gallery_model.rowCount() > 0
        ):
            return
        if (text or not filters.is_empty()) and self._workspace_mode != "collections":
            # Search is a new catalog view. Latest-import IDs otherwise take
            # precedence in _CatalogWorker and silently bypass the query.
            self._import_public_ids = ()
            self._set_active_view(None, None, None)
            library_index = self._view_selector.findData("library")
            if library_index >= 0:
                self._view_selector.blockSignals(True)
                self._view_selector.setCurrentIndex(library_index)
                self._view_selector.blockSignals(False)
        self._search_text = text
        self._search_scope_value = scope
        self._active_filters = filters
        self.refresh()

    def _run_views_operation(self, operation: str, **kwargs: object) -> None:
        thread = QThread(self)
        worker = _ViewsWorker(self._views_service, operation, **kwargs)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.loaded.connect(self._views_loaded)
        worker.completed.connect(self._views_completed)
        worker.failed.connect(self._views_failed)
        worker.loaded.connect(thread.quit)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        self._track(thread, worker)
        thread.start()

    @Slot()
    def refresh_views(self) -> None:
        self._run_views_operation("load")

    @Slot(object, object)
    def _views_loaded(self, saved: tuple[object, ...], collections: tuple[object, ...]) -> None:
        self._collection_records = tuple(collections)
        selected_saved = self._saved_searches.currentData()
        selected_collection = self._collections.currentData()
        self._saved_searches.clear()
        self._saved_searches.addItem("Saved searches…", None)
        for item in saved:
            self._saved_searches.addItem(str(item.name), str(item.public_id))
        self._collections.clear()
        self._collections.addItem("Collections…", None)
        for item in collections:
            kind = str(item.collection_type)
            count = item.asset_count
            suffix = "Smart" if kind == "smart" else str(count)
            label = f"{item.name} ({suffix})"
            self._collections.addItem(label, str(item.public_id))
            index = self._collections.count() - 1
            self._collections.setItemData(index, item, Qt.ItemDataRole.UserRole + 1)
        for combo, value in (
            (self._saved_searches, selected_saved),
            (self._collections, selected_collection),
        ):
            index = combo.findData(value)
            if index >= 0:
                combo.setCurrentIndex(index)

    @Slot(str)
    def _views_completed(self, message: str) -> None:
        self._active_view.setText(message)
        self.refresh_views()

    @Slot(str)
    def _views_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Saved views", message)

    @Slot()
    def save_current_search(self) -> None:
        text = " ".join(self._search_input.text().split())
        filters = self._current_filters()
        if not text and filters.is_empty():
            QMessageBox.information(
                self, "Save search", "Enter search text or enable at least one filter first."
            )
            return
        name, accepted = QInputDialog.getText(self, "Save current search", "Name")
        if accepted and name.strip():
            self._run_views_operation("save_search", name=name, text=text, filters=filters)

    @Slot()
    def delete_saved_search(self) -> None:
        public_id = self._saved_searches.currentData()
        if not public_id:
            return
        if (
            QMessageBox.question(self, "Delete saved search", "Delete the selected saved search?")
            == QMessageBox.StandardButton.Yes
        ):
            self._run_views_operation("delete_search", public_id=str(public_id))
            if self._active_view_kind == "saved" and self._active_view_id == public_id:
                self.clear_active_view()

    @Slot()
    def open_saved_search(self) -> None:
        public_id = self._saved_searches.currentData()
        if public_id:
            self._set_active_view("saved", str(public_id), self._saved_searches.currentText())
            self.refresh()

    @Slot()
    def create_collection(self) -> None:
        name, accepted = QInputDialog.getText(self, "New collection", "Name")
        if accepted and name.strip():
            self._run_views_operation("create_collection", name=name, description=None)

    @Slot()
    def create_smart_collection(self) -> None:
        text = " ".join(self._search_input.text().split())
        filters = self._current_filters()
        if not text and filters.is_empty():
            QMessageBox.information(
                self, "Smart collection", "Enter search text or enable at least one filter first."
            )
            return
        name, accepted = QInputDialog.getText(self, "New smart collection", "Name")
        if accepted and name.strip():
            self._run_views_operation(
                "create_smart_collection", name=name, text=text, filters=filters, description=None
            )

    @Slot()
    def edit_collection(self) -> None:
        public_id = self._collections.currentData()
        if not public_id:
            return
        item = self._collections.currentData(Qt.ItemDataRole.UserRole + 1)
        current_name = str(getattr(item, "name", self._collections.currentText().split(" (")[0]))
        current_description = str(getattr(item, "description", "") or "")
        name, accepted = QInputDialog.getText(self, "Edit collection", "Name", text=current_name)
        if not accepted or not name.strip():
            return
        description, accepted = QInputDialog.getMultiLineText(
            self, "Edit collection", "Description", current_description
        )
        if accepted:
            self._run_views_operation(
                "update_collection", public_id=str(public_id), name=name, description=description
            )

    @Slot()
    def delete_collection(self) -> None:
        public_id = self._collections.currentData()
        if not public_id:
            return
        if (
            QMessageBox.question(
                self,
                "Delete collection",
                "Delete the selected collection? Photographs are not deleted.",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self._run_views_operation("delete_collection", public_id=str(public_id))
            if self._active_view_kind == "collection" and self._active_view_id == public_id:
                self.clear_active_view()

    @Slot()
    def remove_selected_from_collection(self) -> None:
        if self._active_view_kind != "collection" or not self._active_view_id:
            QMessageBox.information(
                self, "Collection", "Open a manual collection before removing members."
            )
            return
        item = self._collections.currentData(Qt.ItemDataRole.UserRole + 1)
        if item is not None and str(getattr(item, "collection_type", "manual")) == "smart":
            QMessageBox.information(
                self, "Collection", "Smart collection membership is defined by its saved query."
            )
            return
        selected = tuple(
            str(row.data(Qt.ItemDataRole.UserRole)) for row in self._grid.selectionModel().selectedIndexes()
        )
        if not selected:
            QMessageBox.information(self, "Collection", "Select one or more assets first.")
            return
        self._run_views_operation(
            "remove_assets", collection_public_id=self._active_view_id, asset_public_ids=selected
        )
        QTimer.singleShot(250, self.refresh)

    @Slot()
    def add_selected_to_collection(self) -> None:
        selected = tuple(
            str(item.data(Qt.ItemDataRole.UserRole)) for item in self._grid.selectionModel().selectedIndexes()
        )
        if not selected:
            QMessageBox.information(self, "Collection", "Select one or more photographs first.")
            return
        manual = tuple(
            item
            for item in self._collection_records
            if str(getattr(item, "collection_type", "manual")) == "manual"
        )
        if not manual:
            QMessageBox.information(self, "Collection", "Create a manual collection first.")
            return
        labels = [str(item.name) for item in manual]
        current_id = self._collections.currentData()
        current_index = next(
            (index for index, item in enumerate(manual) if str(item.public_id) == str(current_id)),
            0,
        )
        label, accepted = QInputDialog.getItem(
            self,
            "Add photographs to collection",
            "Manual collection",
            labels,
            current_index,
            False,
        )
        if not accepted:
            return
        target = manual[labels.index(label)]
        public_id = str(target.public_id)
        self._run_views_operation(
            "add_assets", collection_public_id=public_id, asset_public_ids=selected
        )

    def add_asset_ids_to_collection(self, asset_public_ids: tuple[str, ...]) -> None:
        """Add an explicit V5 selection without depending on this grid's selection state."""
        selected = tuple(dict.fromkeys(str(value) for value in asset_public_ids if value))
        if not selected:
            QMessageBox.information(self, "Collection", "Select one or more assets first.")
            return
        manual = tuple(
            item for item in self._collection_records
            if str(getattr(item, "collection_type", "manual")) == "manual"
        )
        if not manual:
            QMessageBox.information(self, "Collection", "Create a manual collection first.")
            return
        labels = [str(item.name) for item in manual]
        label, accepted = QInputDialog.getItem(
            self, "Add evidence to collection", "Manual collection", labels, 0, False
        )
        if not accepted:
            return
        target = manual[labels.index(label)]
        self._run_views_operation(
            "add_assets",
            collection_public_id=str(target.public_id),
            asset_public_ids=selected,
        )

    @Slot()
    def focus_collections(self) -> None:
        # Collections is a chooser, not an alias for the complete Library.
        # Invalidate an in-flight Library page before clearing it so a late
        # result cannot make newly imported assets appear to be members.
        self._page_request_id += 1
        self._import_public_ids = ()
        self._set_active_view("collection-browser", None, "Collections")
        self._gallery_model.clear()
        self._thumbnail_inputs.clear()
        self._failed_thumbnails.clear()
        self._thumbnail_queue.clear()
        self._count.setText("No collection selected")
        self._preview.setText("Select a collection and choose Open")
        self._technical.clear()
        self._collections.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._active_view.setText(
            "Select a collection and choose Open. New imports remain in Library until explicitly assigned."
        )

    @Slot()
    def open_collection(self) -> None:
        public_id = self._collections.currentData()
        if public_id:
            self._set_active_view("collection", str(public_id), self._collections.currentText())
            self.refresh()

    @Slot()
    def clear_active_view(self) -> None:
        self._import_public_ids = ()
        self._set_active_view(None, None, None)
        index = self._view_selector.findData("library")
        if index >= 0 and self._view_selector.currentIndex() != index:
            self._view_selector.blockSignals(True)
            self._view_selector.setCurrentIndex(index)
            self._view_selector.blockSignals(False)
        self.refresh()

    @Slot(int)
    def _view_selection_changed(self, _index: int) -> None:
        value = self._view_selector.currentData()
        if value == "latest-import" and self._import_public_ids:
            self._set_active_view("import", None, f"Latest import ({len(self._import_public_ids)})")
            self.refresh()
            return
        if value == "library" and self._active_view_kind == "import":
            self.clear_active_view()

    def _set_active_view(self, kind: str | None, public_id: str | None, name: str | None) -> None:
        self._active_view_kind = kind
        self._active_view_id = public_id
        self._active_view_name = name
        self._active_view.setText(f"Active view: {name}" if name else "")
        self._clear_view.setEnabled(kind is not None)

    def _current_filters(self) -> StructuredAssetFilters:
        return StructuredAssetFilters(
            minimum_rating=self._minimum_rating.currentData(),
            color_label=self._filter_color.currentData(),
            pick_state=self._filter_pick.currentData(),
            captured_from_date=(
                self._date_from.date().toString("yyyy-MM-dd")
                if self._date_from_enabled.isChecked()
                else None
            ),
            captured_to_date=(
                self._date_to.date().toString("yyyy-MM-dd")
                if self._date_to_enabled.isChecked()
                else None
            ),
            minimum_width=self._minimum_width.value() or None,
            minimum_height=self._minimum_height.value() or None,
            tag=self._filter_tag.text().strip() or None,
            taxonomy_name=self._filter_taxonomy.text().strip() or None,
            camera_make=self._filter_camera_make.text().strip() or None,
            camera_model=self._filter_camera_model.text().strip() or None,
            lens=self._filter_lens.text().strip() or None,
            minimum_latitude=self._gps_south.value()
            if self._gps_bounds_enabled.isChecked()
            else None,
            maximum_latitude=self._gps_north.value()
            if self._gps_bounds_enabled.isChecked()
            else None,
            minimum_longitude=self._gps_west.value()
            if self._gps_bounds_enabled.isChecked()
            else None,
            maximum_longitude=self._gps_east.value()
            if self._gps_bounds_enabled.isChecked()
            else None,
            exact_duplicates_only=True if self._exact_duplicates_only.isChecked() else None,
        )

    @Slot()
    def clear_filters(self) -> None:
        self._minimum_rating.setCurrentIndex(0)
        self._filter_color.setCurrentIndex(0)
        self._filter_pick.setCurrentIndex(0)
        self._date_from_enabled.setChecked(False)
        self._date_to_enabled.setChecked(False)
        self._minimum_width.setValue(0)
        self._minimum_height.setValue(0)
        self._filter_tag.clear()
        self._filter_taxonomy.clear()
        self._filter_camera_make.clear()
        self._filter_camera_model.clear()
        self._filter_lens.clear()
        self._gps_bounds_enabled.setChecked(False)
        self._gps_south.setValue(-90.0)
        self._gps_north.setValue(90.0)
        self._gps_west.setValue(-180.0)
        self._gps_east.setValue(180.0)
        self._exact_duplicates_only.setChecked(False)
        self._apply_search()

    def show_imported(self, public_ids: tuple[str, ...], *, imported: int, failed: int) -> None:
        normalized_ids = tuple(dict.fromkeys(public_ids))
        if not normalized_ids:
            # A zero-import result must not create an implicit empty Latest import
            # view or replace the user's current catalog state.
            self._pending_import_sync = {
                "status": "import-completed",
                "imported": imported,
                "failed": failed,
                "requested_assets": 0,
            }
            self.clear_active_view()
            return
        self._import_public_ids = normalized_ids
        self._search_text = ""
        self._active_filters = StructuredAssetFilters()
        latest_index = self._view_selector.findData("latest-import")
        label = f"Latest import ({len(self._import_public_ids)})"
        if latest_index < 0:
            self._view_selector.addItem(label, "latest-import")
            latest_index = self._view_selector.findData("latest-import")
        else:
            self._view_selector.setItemText(latest_index, label)
        self._view_selector.blockSignals(True)
        self._view_selector.setCurrentIndex(latest_index)
        self._view_selector.blockSignals(False)
        self._set_active_view("import", None, label)
        self._pending_import_sync = {
            "status": "import-completed",
            "imported": imported,
            "failed": failed,
            "requested_assets": len(self._import_public_ids),
        }
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        # A newer filter request supersedes an in-flight page. Request IDs make
        # late results harmless, so the latest query must not be discarded.
        self._refreshing = True
        self._next_cursor = None
        self._page_request_id += 1
        self._request_page(after_id=None, append=False, request_id=self._page_request_id)

    @Slot()
    def load_more(self) -> None:
        if self._refreshing or self._next_cursor is None:
            return
        self._refreshing = True
        self._request_page(
            after_id=self._next_cursor, append=True, request_id=self._page_request_id
        )

    @Slot(int)
    def _gallery_scrolled(self, value: int) -> None:
        """Pause thumbnail IO until wheel or scrollbar movement has settled."""
        if value != self._last_scroll_value:
            self._scroll_direction = 1 if value > self._last_scroll_value else -1
        self._last_scroll_value = value
        self._scrolling = True
        self._scroll_idle_timer.start()
        # Discard speculative work for the old viewport. Already-running jobs
        # are allowed to finish, but cannot drain more work while scrolling.
        self._thumbnail_queue.clear()
        self._thumbnail_queued.clear()

    @Slot()
    def _scrolling_stopped(self) -> None:
        self._scroll_idle_timer.stop()
        self._scrolling = False
        self._schedule_visible_thumbnails()
        self._load_more_if_needed()

    def _load_more_if_needed(self) -> None:
        if self._refreshing or self._next_cursor is None:
            return
        scrollbar = self._grid.verticalScrollBar()
        threshold = max(120, self._grid.gridSize().height())
        if scrollbar.maximum() <= threshold or scrollbar.value() >= scrollbar.maximum() - threshold:
            self.load_more()

    def _request_page(self, *, after_id: int | None, append: bool, request_id: int) -> None:
        self._refresh.setEnabled(False)
        self._more.setEnabled(False)
        self._retry_thumbnails.setEnabled(False)
        self._count.setText("Loading…")
        thread = QThread(self)
        worker = _CatalogWorker(
            self._catalog,
            self._search_service,
            self._views_service,
            search_text=self._search_text,
            filters=self._active_filters,
            after_id=after_id,
            append=append,
            request_id=request_id,
            view_kind=self._active_view_kind,
            view_public_id=self._active_view_id,
            import_public_ids=self._import_public_ids,
            search_scope=str(self._search_scope.currentData() or "all"),
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.page_ready.connect(self._page_ready)
        worker.failed.connect(self._page_failed)
        worker.page_ready.connect(thread.quit)
        worker.failed.connect(thread.quit)
        self._track(thread, worker)
        thread.start()

    @Slot(object, bool, int)
    def _page_ready(self, page: AssetPage, append: bool, request_id: int) -> None:
        if request_id != self._page_request_id:
            return
        self._refreshing = False
        if not append:
            self._gallery_model.clear()
            self._thumbnail_inputs.clear()
            self._failed_thumbnails.clear()
            self._thumbnail_queue.clear()
            self._thumbnail_queued.clear()
            self._thumbnail_inflight.clear()
            self._thumbnail_loaded.clear()
            self._retry_thumbnails.setEnabled(False)
        rows = tuple(page.rows)
        self._gallery_model.append_rows(rows)
        for row in rows:
            self._thumbnail_inputs[str(row.public_id)] = (
                Path(row.primary_path) if row.primary_path else None,
                Path(row.thumbnail_path) if row.thumbnail_path else None,
            )
        self._next_cursor = page.next_cursor
        noun = (
            "result"
            if self._active_view_kind or self._search_text or not self._active_filters.is_empty()
            else "asset"
        )
        self._count.setText(f"{page.total_count} {noun}{'s' if page.total_count != 1 else ''}")
        self._refresh.setEnabled(True)
        self._more.setEnabled(self._next_cursor is not None)
        QTimer.singleShot(0, self._schedule_visible_thumbnails)
        QTimer.singleShot(0, self._load_more_if_needed)
        if not append and self._pending_import_sync is not None:
            payload = dict(self._pending_import_sync)
            payload.update(
                {
                    "created_at_utc": datetime.now(UTC).isoformat(),
                    "database_assets": page.total_count,
                    "model_assets": self._gallery_model.rowCount(),
                    "synchronized": self._gallery_model.rowCount() == len(self._import_public_ids),
                }
            )
            log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Aperture" / "Logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "import-sync.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True) + "\n")
            self._pending_import_sync = None

    def _schedule_visible_thumbnails(self) -> None:
        if not self._active or self._scrolling or self._gallery_model.rowCount() == 0:
            return
        viewport = self._grid.viewport().rect()
        first = self._grid.indexAt(viewport.topLeft())
        last = self._grid.indexAt(viewport.bottomRight())
        first_row = first.row() if first.isValid() else 0
        last_row = last.row() if last.isValid() else min(self._gallery_model.rowCount() - 1, first_row + 24)
        # Decode only the viewport and a modest directional look-ahead. The
        # previous 400-row prefetch caused continual QThread creation and disk
        # reads while background derivative generation was also active.
        if self._scroll_direction >= 0:
            start_row = max(0, first_row - 4)
            end_row = min(self._gallery_model.rowCount(), last_row + 1 + 12)
        else:
            start_row = max(0, first_row - 12)
            end_row = min(self._gallery_model.rowCount(), last_row + 1 + 4)
        available_slots = max(
            0,
            self._thumbnail_queue_limit
            - len(self._thumbnail_queue)
            - len(self._thumbnail_inflight),
        )
        for row in range(start_row, end_row):
            if available_slots <= 0:
                break
            index = self._gallery_model.index(row, 0)
            public_id = str(index.data(_GalleryModel.PublicIdRole))
            if public_id in self._thumbnail_loaded or public_id in self._thumbnail_queued or public_id in self._thumbnail_inflight:
                continue
            source, cached = self._thumbnail_inputs.get(public_id, (None, None))
            self._thumbnail_queue.append((public_id, source, cached))
            self._thumbnail_queued.add(public_id)
            available_slots -= 1
        self._drain_thumbnail_queue()
        self._update_thumbnail_status()

    @Slot()
    def _poll_pending_thumbnails(self) -> None:
        """Recheck visible cache entries without decoding originals in the GUI."""
        if self._scrolling or not self._active:
            return
        self._schedule_visible_thumbnails()

    def _request_thumbnail(self, public_id: str, source: Path | None, cached: Path | None) -> None:
        if public_id in self._thumbnail_loaded or public_id in self._thumbnail_queued or public_id in self._thumbnail_inflight:
            return
        self._thumbnail_queue.append((public_id, source, cached))
        self._thumbnail_queued.add(public_id)
        self._drain_thumbnail_queue()

    def _drain_thumbnail_queue(self) -> None:
        if self._scrolling:
            return
        while self._thumbnail_queue and self._thumbnail_active < self._thumbnail_limit:
            public_id, source, cached = self._thumbnail_queue.popleft()
            self._thumbnail_queued.discard(public_id)
            if not self._gallery_model.index_for_public_id(public_id).isValid():
                continue
            self._thumbnail_inflight.add(public_id)
            thread = QThread(self)
            worker = _ThumbnailWorker(self._thumbnails, self._catalog, public_id, source, cached)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.ready.connect(self._thumbnail_ready)
            worker.ready.connect(thread.quit)
            self._thumbnail_active += 1
            self._track(thread, worker)
            thread.start()
        self._update_thumbnail_status()

    def _update_thumbnail_status(self) -> None:
        queued = len(self._thumbnail_queue)
        active = self._thumbnail_active
        waiting = max(
            0,
            self._gallery_model.rowCount()
            - len(self._thumbnail_loaded)
            - len(self._failed_thumbnails),
        )
        if active or queued:
            self._thumbnail_status.setText(
                f"Thumbnails: {active} checking · {queued} queued · work in background"
            )
        elif waiting:
            self._thumbnail_status.setText(
                f"Thumbnails: {waiting} awaiting background generation"
            )
        else:
            self._thumbnail_status.setText("Thumbnails ready")

    @Slot(str, object)
    def _thumbnail_ready(self, public_id: str, data: bytes | None) -> None:
        self._thumbnail_active = max(0, self._thumbnail_active - 1)
        self._thumbnail_inflight.discard(public_id)
        index = self._gallery_model.index_for_public_id(public_id)
        if index.isValid():
            if not data:
                placeholder = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
                self._gallery_model.set_thumbnail(
                    public_id,
                    placeholder,
                    "Thumbnail queued in background; you can continue working",
                )
            else:
                pixmap = QPixmap()
                if pixmap.loadFromData(QByteArray(data)):
                    self._gallery_model.set_thumbnail(public_id, QIcon(pixmap), "Thumbnail ready")
                    self._thumbnail_loaded.add(public_id)
                    self._failed_thumbnails.discard(public_id)
                    self._retry_thumbnails.setEnabled(bool(self._failed_thumbnails))
                else:
                    self._failed_thumbnails.add(public_id)
                    warning = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
                    self._gallery_model.set_thumbnail(public_id, warning, "Thumbnail decode failed")
                    self._retry_thumbnails.setEnabled(True)
        self._drain_thumbnail_queue()
        self._update_thumbnail_status()
        # Refill asynchronously after one serial read completes. This keeps the
        # event loop responsive and never grows the queue beyond its cap.
        QTimer.singleShot(0, self._schedule_visible_thumbnails)

    @Slot()
    def retry_failed_thumbnails(self) -> None:
        failed = tuple(self._failed_thumbnails)
        self._failed_thumbnails.clear()
        self._retry_thumbnails.setEnabled(False)
        for public_id in failed:
            item = self._gallery_model.index_for_public_id(public_id)
            inputs = self._thumbnail_inputs.get(public_id)
            if not item.isValid() or inputs is None:
                continue
            self._thumbnail_loaded.discard(public_id)
            self._gallery_model.set_thumbnail(public_id, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon), "Retrying thumbnail")
            self._request_thumbnail(public_id, *inputs)

    @Slot()
    def _run_photo_capability(self) -> None:
        if self._enrichment_controller is None:
            return
        from natureai_next.domain.enrichment import SubjectRef, SubjectType
        from natureai_next.synthesis_core.contracts import InputKind
        from natureai_next.ui.qt.capability_execution import CapabilityExecutionDialog

        choices = self._enrichment_controller.capabilities_for(InputKind.PHOTO)
        if not choices:
            QMessageBox.information(
                self, "Run enrichment", "No enabled model accepts photograph input."
            )
            return
        selected = tuple(self._grid.selectionModel().selectedIndexes())
        if not selected:
            return
        current_id = str(selected[0].data(_GalleryModel.PublicIdRole))
        inputs = self._thumbnail_inputs.get(current_id)
        source_path = inputs[0] if inputs else None
        dialog = CapabilityExecutionDialog(
            choices, input_kind=InputKind.PHOTO, input_path=source_path, parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.request is None:
            return
        request = dialog.request
        if request.region_classifier_id:
            if len(selected) > 1:
                QMessageBox.information(
                    self,
                    "Region pipeline",
                    "Parallel region pipelines require the detector and classifier batch "
                    "screen. Choose a direct photo capability for this batch.",
                )
                return
            subject = SubjectRef(SubjectType.PHOTO, current_id)
            try:
                self._capability_run = (
                    self._enrichment_controller.run_region_pipeline_async(
                        subject,
                        detector_id=request.capability_id,
                        classifier_id=request.region_classifier_id,
                        input_path=request.input_path,
                        detector_parameters=request.parameters,
                    )
                )
            except Exception as exc:
                QMessageBox.critical(self, "Enrichment failed", str(exc))
                return
            self._run_capability.setEnabled(False)
            self._capability_progress = QProgressDialog(
                f"Running {request.capability_id}", "Cancel", 0, 3, self
            )
            self._capability_progress.setWindowTitle("Photo region enrichment")
            self._capability_progress.setWindowModality(Qt.WindowModality.WindowModal)
            self._capability_progress.canceled.connect(self._capability_run.cancel)
            self._capability_progress.show()
            self._capability_timer.start()
            return
        from natureai_next.application.enrichment_workspace import WorkspaceBatchItem
        from natureai_next.ui.qt.capability_execution import CapabilityBatchProgressDialog

        batch_items = []
        batch_labels = []
        for index in selected:
            public_id = str(index.data(_GalleryModel.PublicIdRole))
            source = self._thumbnail_inputs.get(public_id, (None, None))[0]
            batch_items.append(
                WorkspaceBatchItem(
                    SubjectRef(SubjectType.PHOTO, public_id),
                    source,
                    request.structured_input,
                )
            )
            batch_labels.append(
                (
                    public_id,
                    str(index.data(Qt.ItemDataRole.DisplayRole) or public_id),
                )
            )
        executions = [(request.capability_id, request.parameters)]
        choices_by_id = {item.descriptor.capability_id: item for item in choices}
        for capability_id in request.additional_capability_ids:
            choice = choices_by_id.get(capability_id)
            if choice is not None:
                executions.append(
                    (
                        capability_id,
                        {
                            definition.name: definition.default
                            for definition in choice.descriptor.parameters
                            if definition.default is not None
                        },
                    )
                )
        self._run_capability.setEnabled(False)
        self._batch_screens = []
        for capability_id, parameters in executions:
            try:
                run = self._enrichment_controller.run_capability_batch_async(
                    tuple(batch_items),
                    capability_id=capability_id,
                    input_kind=request.input_kind,
                    parameters=parameters,
                    # Each optional model execution owns a heavyweight worker process.
                    # Four simultaneous launches make large selections slower through
                    # model-load, VRAM and disk contention; two keeps useful overlap.
                    max_parallel=min(2, len(batch_items)),
                )
            except Exception as exc:
                QMessageBox.warning(self, f"{capability_id} failed to start", str(exc))
                continue
            screen = CapabilityBatchProgressDialog(
                run,
                tuple(batch_labels),
                capability_name=capability_id,
                library_name="Photos",
                parent=None,
            )
            screen.completed.connect(self._photo_batch_finished)
            screen.show()
            self._batch_screens.append(screen)
        self._batch_screen = self._batch_screens[-1] if self._batch_screens else None

    @Slot(object)
    def _photo_batch_finished(self, _outcome) -> None:
        if self._enrichment_panel is not None:
            self._enrichment_panel.refresh()
        if not any(screen.running for screen in self._batch_screens):
            self._run_capability.setEnabled(
                self._workspace_enabled and bool(self._grid.selectionModel().selectedIndexes())
            )

    def set_workspace_enabled(self, enabled: bool) -> None:
        self._workspace_enabled = bool(enabled)
        if not enabled and self._batch_screens:
            for screen in self._batch_screens:
                screen.cancel_for_disabled_workspace()
                screen.hide()
        elif enabled and self._batch_screen is not None and self._batch_screen.running:
            for screen in self._batch_screens:
                if screen.running:
                    screen.show()
        self._run_capability.setEnabled(
            enabled
            and self._enrichment_controller is not None
            and bool(self._grid.selectionModel().selectedIndexes())
        )

    @Slot()
    def _poll_photo_capability(self) -> None:
        run = self._capability_run
        if run is None:
            self._capability_timer.stop()
            return
        progress = run.progress
        if self._capability_progress is not None:
            total = progress.total or 0
            self._capability_progress.setRange(0, total)
            self._capability_progress.setValue(min(progress.current, total) if total else 0)
            self._capability_progress.setLabelText(progress.message)
        if not run.done:
            return
        self._capability_timer.stop()
        if self._capability_progress is not None:
            self._capability_progress.close()
        try:
            run.result()
        except InterruptedError:
            pass
        except Exception as exc:
            QMessageBox.critical(self, "Enrichment failed", str(exc))
        else:
            if self._enrichment_panel is not None:
                self._enrichment_panel.refresh()
        finally:
            self._capability_run = None
            self._capability_progress = None
            self._run_capability.setEnabled(bool(self._grid.selectionModel().selectedIndexes()))

    @Slot()
    def _selection_changed(self) -> None:
        if self._selection_guard:
            return
        selected = self._grid.selectionModel().selectedIndexes()
        if selected:
            self._last_selected_asset_ids = tuple(
                str(item.data(Qt.ItemDataRole.UserRole)) for item in selected
            )
        self._open_viewer.setEnabled(bool(selected))
        self._run_capability.setEnabled(
            self._workspace_enabled
            and bool(selected)
            and self._enrichment_controller is not None
            and self._capability_run is None
            and not (self._batch_screen is not None and self._batch_screen.running)
        )
        maintenance_enabled = self._maintenance_service is not None and bool(selected)
        self._trash_selected.setEnabled(maintenance_enabled)
        self._apply_batch_review.setEnabled(len(selected) >= 2)
        self._photo_box.setVisible(len(selected) == 1)
        self._batch_box.setVisible(len(selected) >= 2)
        if not selected:
            if self._inspector_button.isChecked():
                self._inspector_button.setChecked(False)
            if self._metadata_dirty and self._detail is not None:
                self._restore_selection(self._detail.public_id)
                return
            self._preview_request_id += 1
            self._selected_public_id = None
            self._preview.setText("No selection")
            self._preview.setPixmap(QPixmap())
            self._technical.clear()
            self._load_editor(None)
            if self._enrichment_panel is not None:
                from natureai_next.domain.enrichment import SubjectRef, SubjectType

                self._enrichment_panel.set_subject(SubjectRef(SubjectType.PHOTO, "__none__"))
            return
        if not self._inspector_button.isChecked():
            self._inspector_button.setChecked(True)
        public_id = str(selected[0].data(Qt.ItemDataRole.UserRole))
        if self._enrichment_panel is not None:
            from natureai_next.domain.enrichment import SubjectRef, SubjectType

            self._enrichment_panel.set_subject(SubjectRef(SubjectType.PHOTO, public_id))
        if (
            self._metadata_dirty
            and self._detail is not None
            and public_id != self._detail.public_id
        ):
            choice = QMessageBox.warning(
                self,
                "Unsaved metadata",
                "Save or discard the current metadata changes before selecting another asset.",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if choice == QMessageBox.StandardButton.Save:
                self._restore_selection(self._detail.public_id)
                self.save_metadata()
                return
            if choice == QMessageBox.StandardButton.Cancel:
                self._restore_selection(self._detail.public_id)
                return
            self._set_metadata_dirty(False)
        self._preview_request_id += 1
        self._preview.setText("Loading preview…")
        self._preview.setPixmap(QPixmap())
        self._request_detail(public_id)

    def _restore_selection(self, public_id: str) -> None:
        item = self._gallery_model.index_for_public_id(public_id)
        if not item.isValid():
            return
        self._selection_guard = True
        try:
            self._grid.clearSelection()
            self._grid.selectionModel().select(item, self._grid.selectionModel().SelectionFlag.Select | self._grid.selectionModel().SelectionFlag.Rows)
            self._grid.setCurrentIndex(item)
        finally:
            self._selection_guard = False

    @Slot(str, object)
    def _detail_ready(self, public_id: str, detail: AssetDetail | None) -> None:
        if public_id != self._selected_public_id:
            return
        if detail is None:
            self._technical.setText("Asset is no longer available.")
            self._load_editor(None)
            return
        dimensions = (
            f"{detail.pixel_width} × {detail.pixel_height}"
            if detail.pixel_width and detail.pixel_height
            else "Unknown dimensions"
        )
        tags = ", ".join(detail.tags) or "None"
        raw_path = detail.primary_path or "Unavailable"
        # Backslashes and path components are not natural HTML break points.
        # Insert zero-width break opportunities so a long original path wraps
        # inside the inspector instead of increasing its minimum width.
        safe_path = html.escape(raw_path).replace("\\", "\\&#8203;").replace("/", "/&#8203;")
        safe_source_path = html.escape(detail.source_path or "Not retained").replace("\\", "\\&#8203;").replace("/", "/&#8203;")
        safe_master_path = html.escape(detail.aperture_master_path or "Not created").replace("\\", "\\&#8203;").replace("/", "/&#8203;")
        self._technical.setText(
            f"<b>{html.escape(detail.title or 'Untitled')}</b><br>"
            f"{dimensions}<br>"
            f"Format: {html.escape(detail.format_name or detail.mime_type or 'Unknown')}<br>"
            f"Rating: {detail.rating if detail.rating is not None else '—'}<br>"
            f"Tags: {html.escape(tags)}<br><br>"
            f"Storage mode: {html.escape({'referenced': 'Linked', 'managed': 'Managed', 'hybrid': 'Hybrid'}.get((detail.storage_mode or '').lower(), 'Unknown'))}<br>"
            f"Availability: {html.escape((detail.availability_state or 'unknown').title())}<br>"
            f"Source file: {safe_source_path}<br>"
            f"Aperture original: {safe_master_path}"
        )
        self._technical.setToolTip("\n".join(x for x in (detail.source_path, detail.aperture_master_path) if x))
        self._load_editor(detail)
        item = self._gallery_model.index_for_public_id(public_id)
        if item is not None:
            item.setText(
                detail.title
                or (Path(detail.primary_path).name if detail.primary_path else public_id)
            )

    @Slot(int, object)
    def _preview_ready(self, request_id: int, data: bytes | None) -> None:
        if request_id != self._preview_request_id:
            return
        if not data:
            self._preview.setText("Preview unavailable")
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(QByteArray(data)):
            self._preview.setText("Preview unavailable")
            return
        self._preview.setPixmap(
            pixmap.scaled(
                self._preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        )

    def _load_editor(self, detail: AssetDetail | None) -> None:
        self._loading_editor = True
        self._detail = detail
        enabled = detail is not None
        for control in (
            self._title,
            self._caption,
            self._notes,
            self._rating,
            self._color,
            self._pick,
            self._tags,
            self._subject_name,
            self._subject_latitude,
            self._subject_longitude,
        ):
            control.setEnabled(enabled)
        if detail is None:
            self._title.clear()
            self._caption.clear()
            self._notes.clear()
            self._rating.setValue(0)
            self._color.setCurrentIndex(0)
            self._pick.setCurrentIndex(0)
            self._tags.clear()
            self._capture_location.setText("No embedded GPS location")
            self._subject_name.clear()
            self._subject_latitude.setValue(-90.0)
            self._subject_longitude.setValue(-180.0)
        else:
            self._title.setText(detail.title or "")
            self._caption.setPlainText(detail.caption or "")
            self._notes.setPlainText(detail.user_notes or "")
            self._rating.setValue(detail.rating or 0)
            self._set_combo_value(self._color, detail.color_label)
            self._set_combo_value(self._pick, detail.pick_state)
            self._tags.setText(", ".join(detail.tags))
            if detail.capture_latitude is not None and detail.capture_longitude is not None:
                place = f" — {detail.capture_place_name}" if detail.capture_place_name else ""
                self._capture_location.setText(
                    f"{detail.capture_latitude:.7f}, {detail.capture_longitude:.7f}{place}"
                )
            else:
                self._capture_location.setText("No embedded GPS location")
            self._subject_name.setText(detail.subject_place_name or "")
            self._subject_latitude.setValue(
                detail.subject_latitude if detail.subject_latitude is not None else -90.0
            )
            self._subject_longitude.setValue(
                detail.subject_longitude if detail.subject_longitude is not None else -180.0
            )
        self._loading_editor = False
        self._set_metadata_dirty(False)

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str | None) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    @Slot()
    def _mark_metadata_dirty(self) -> None:
        if not self._loading_editor and self._detail is not None:
            self._set_metadata_dirty(True)

    def _set_metadata_dirty(self, dirty: bool) -> None:
        self._metadata_dirty = dirty
        self._save_metadata.setEnabled(dirty and self._detail is not None)
        self._discard_metadata.setEnabled(dirty and self._detail is not None)

    @Slot()
    def discard_metadata(self) -> None:
        if self._detail is not None and self._metadata_dirty:
            self._load_editor(self._detail)

    @Slot()
    def save_metadata(self) -> None:
        detail = self._detail
        if detail is None or not self._metadata_dirty:
            return
        title = self._title.text().strip() or None
        caption = self._caption.toPlainText().strip() or None
        notes = self._notes.toPlainText().strip() or None
        if title is not None and len(title) > 500:
            QMessageBox.warning(self, "Invalid metadata", "Title cannot exceed 500 characters.")
            return
        if caption is not None and len(caption) > 10000:
            QMessageBox.warning(
                self, "Invalid metadata", "Caption cannot exceed 10,000 characters."
            )
            return
        if notes is not None and len(notes) > 50000:
            QMessageBox.warning(self, "Invalid metadata", "Notes cannot exceed 50,000 characters.")
            return
        patch = MetadataPatch(
            title=title,
            caption=caption,
            user_notes=notes,
            rating=self._rating.value() or None,
            color_label=self._color.currentData(),
            pick_state=self._pick.currentData(),
        )
        tags = tuple(part.strip() for part in self._tags.text().split(",") if part.strip())
        self._save_metadata.setEnabled(False)
        self._discard_metadata.setEnabled(False)
        thread = QThread(self)
        worker = _MetadataSaveWorker(
            self._editor,
            public_id=detail.public_id,
            expected_revision=detail.revision,
            patch=patch,
            tag_names=tags,
            subject_latitude=None
            if self._subject_latitude.value() == -90.0 and not self._subject_name.text().strip()
            else self._subject_latitude.value(),
            subject_longitude=None
            if self._subject_longitude.value() == -180.0 and not self._subject_name.text().strip()
            else self._subject_longitude.value(),
            subject_place_name=self._subject_name.text().strip() or None,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.saved.connect(self._metadata_saved)
        worker.failed.connect(self._metadata_save_failed)
        worker.saved.connect(thread.quit)
        worker.failed.connect(thread.quit)
        self._track(thread, worker)
        thread.start()

    @Slot()
    def apply_batch_review(self) -> None:
        selected = self._grid.selectionModel().selectedIndexes()
        if len(selected) < 2:
            QMessageBox.information(self, "Batch update", "Select at least two photographs first.")
            return
        changes: dict[str, object] = {}
        text_values = {
            "title": self._batch_title.text(),
            "caption": self._batch_caption.toPlainText(),
            "user_notes": self._batch_notes.toPlainText(),
        }
        for key, value in text_values.items():
            if value.strip():
                changes[key] = value.strip()
        for key, combo in (("rating", self._batch_rating), ("color_label", self._batch_color), ("pick_state", self._batch_pick)):
            value = combo.currentData()
            if value != "unchanged":
                changes[key] = value
        if self._batch_tags.text().strip():
            changes["tags"] = tuple(part.strip() for part in self._batch_tags.text().split(",") if part.strip())
        subject_name = self._batch_subject_name.text().strip()
        lat_text = self._batch_subject_latitude.text().strip()
        lon_text = self._batch_subject_longitude.text().strip()
        if subject_name:
            changes["subject_place_name"] = subject_name
        try:
            if lat_text:
                latitude = float(lat_text)
                if not -90 <= latitude <= 90:
                    raise ValueError("Latitude must be between -90 and 90.")
                changes["subject_latitude"] = latitude
            if lon_text:
                longitude = float(lon_text)
                if not -180 <= longitude <= 180:
                    raise ValueError("Longitude must be between -180 and 180.")
                changes["subject_longitude"] = longitude
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid geolocation", str(exc))
            return
        if not changes:
            QMessageBox.information(self, "Batch update", "Enter at least one value to change.")
            return
        targets = tuple(
            BatchReviewTarget(
                str(item.data(Qt.ItemDataRole.UserRole)),
                int(item.data(Qt.ItemDataRole.UserRole + 1)),
            )
            for item in selected
        )
        self._apply_batch_review.setEnabled(False)
        thread = QThread(self)
        worker = _BatchReviewWorker(self._catalog, self._editor, targets=targets, changes=changes)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.saved.connect(self._batch_review_saved)
        worker.failed.connect(self._batch_review_failed)
        worker.saved.connect(thread.quit)
        worker.failed.connect(thread.quit)
        self._track(thread, worker)
        thread.start()

    @Slot(int)
    def _batch_review_saved(self, count: int) -> None:
        QMessageBox.information(self, "Batch review", f"Updated {count} photographs.")
        self._batch_title.clear()
        self._batch_caption.clear()
        self._batch_notes.clear()
        self._batch_rating.setCurrentIndex(0)
        self._batch_color.setCurrentIndex(0)
        self._batch_pick.setCurrentIndex(0)
        self._batch_tags.clear()
        self._batch_subject_name.clear()
        self._batch_subject_latitude.clear()
        self._batch_subject_longitude.clear()
        self.refresh()

    @Slot(str)
    def _batch_review_failed(self, message: str) -> None:
        if "asset_revision_conflict" in message:
            QMessageBox.warning(
                self,
                "Photographs changed elsewhere",
                "The selection changed after loading. No photographs were updated; the Library will refresh.",
            )
            self.refresh()
        else:
            QMessageBox.critical(self, "Could not apply batch review", message)
            self._selection_changed()

    @Slot(str)
    def _metadata_saved(self, public_id: str) -> None:
        if public_id != self._selected_public_id:
            return
        self._set_metadata_dirty(False)
        self._request_detail(public_id)

    @Slot(str, str)
    def _metadata_save_failed(self, public_id: str, message: str) -> None:
        if public_id == self._selected_public_id:
            self._save_metadata.setEnabled(True)
            self._discard_metadata.setEnabled(True)
        if "asset_revision_conflict" in message:
            QMessageBox.warning(
                self,
                "Metadata changed elsewhere",
                "This asset changed after it was loaded. The latest values will be reloaded.",
            )
            self._request_detail(public_id)
        else:
            QMessageBox.critical(self, "Could not save metadata", message)

    def _request_detail(self, public_id: str) -> None:
        self._preview_request_id += 1
        self._selected_public_id = public_id
        thread = QThread(self)
        worker = _DetailWorker(self._catalog, public_id)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.ready.connect(self._detail_ready)
        worker.failed.connect(self._failed)
        worker.ready.connect(thread.quit)
        worker.failed.connect(thread.quit)
        self._track(thread, worker)
        thread.start()

    @Slot()
    def _run_maintenance_operation(
        self,
        operation: str,
        asset_public_ids: tuple[str, ...],
        *,
        observation_policy: Literal["block", "unlink", "delete"] = "block",
    ) -> None:
        if self._maintenance_service is None:
            return
        self._trash_selected.setEnabled(False)
        self._pending_maintenance_ids = asset_public_ids
        thread = QThread(self)
        worker = _MaintenanceWorker(
            self._maintenance_service,
            operation,
            asset_public_ids,
            observation_policy=observation_policy,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._maintenance_completed)
        worker.failed.connect(self._maintenance_failed)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        self._track(thread, worker)
        thread.start()

    @Slot(str, object)
    def _maintenance_completed(self, operation: str, payload: object) -> None:
        affected_ids = set(self._pending_maintenance_ids)
        self._pending_maintenance_ids = ()
        self._selection_guard = True
        try:
            removed_ids = self._gallery_model.remove_public_ids(affected_ids)
        finally:
            self._selection_guard = False
        if removed_ids:
            removed_set = set(removed_ids)
            self._thumbnail_inputs = {
                public_id: inputs
                for public_id, inputs in self._thumbnail_inputs.items()
                if public_id not in removed_set
            }
            self._failed_thumbnails.difference_update(removed_set)
            self._thumbnail_queued.difference_update(removed_set)
            self._thumbnail_inflight.difference_update(removed_set)
            self._thumbnail_loaded.difference_update(removed_set)
            self._thumbnail_queue = deque(
                job for job in self._thumbnail_queue if job[0] not in removed_set
            )
        if operation == "trash":
            changed = int(payload)
            self._count.setText(f"Moved {changed} photograph{'s' if changed != 1 else ''} to Trash")
        else:
            results = tuple(payload)
            deleted_files = sum(int(getattr(item, "deleted_files", 0)) for item in results)
            deleted_analyses = sum(int(getattr(item, "deleted_analyses", 0)) for item in results)
            QMessageBox.information(
                self,
                "Permanent deletion complete",
                f"Deleted {len(results)} photograph(s), {deleted_files} managed file(s), "
                f"and {deleted_analyses} analysis record(s).",
            )
        self._selection_changed()
        QTimer.singleShot(0, self._schedule_visible_thumbnails)
        QTimer.singleShot(0, self._load_more_if_needed)

    @Slot(str)
    def _maintenance_failed(self, message: str) -> None:
        self._pending_maintenance_ids = ()
        QMessageBox.critical(self, "Photograph removal", message)
        self._selection_changed()

    @Slot()
    def trash_selected_assets(self) -> None:
        if self._maintenance_service is None:
            return
        selected = tuple(
            str(item.data(Qt.ItemDataRole.UserRole)) for item in self._grid.selectionModel().selectedIndexes()
        )
        if not selected:
            return
        count = len(selected)
        answer = QMessageBox.question(
            self,
            "Move photographs to Trash",
            f"Move {count} selected photograph{'s' if count != 1 else ''} to Trash?\n\n"
            "Files and analyses are retained and can be restored.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_maintenance_operation("trash", selected)

    def _removal_summary(self, previews: tuple[object, ...]) -> str:
        analyses = sum(int(getattr(item, "analysis_count", 0)) for item in previews)
        suggestions = sum(int(getattr(item, "suggestion_count", 0)) for item in previews)
        observations = sum(int(getattr(item, "observation_count", 0)) for item in previews)
        promotions = sum(int(getattr(item, "promotion_count", 0)) for item in previews)
        files = sum(len(getattr(item, "managed_files", ())) for item in previews)
        derivatives = sum(len(getattr(item, "derivative_files", ())) for item in previews)
        jobs = sum(int(getattr(item, "running_job_count", 0)) for item in previews)
        return (
            f"Photographs: {len(previews)}\n"
            f"Managed files: {files}\n"
            f"Thumbnails/previews: {derivatives}\n"
            f"AI analyses: {analyses}\n"
            f"AI suggestions: {suggestions}\n"
            f"Linked observations: {observations}\n"
            f"Analysis promotions: {promotions}\n"
            f"Running or queued jobs: {jobs}"
        )

    @Slot()
    def permanently_delete_selected_assets(self) -> None:
        if self._maintenance_service is None:
            return
        selected = tuple(
            str(item.data(Qt.ItemDataRole.UserRole)) for item in self._grid.selectionModel().selectedIndexes()
        )
        if not selected:
            return
        previews = tuple(
            self._maintenance_service.removal_preview(public_id) for public_id in selected
        )
        dependencies = any(
            bool(getattr(item, "has_authoritative_dependencies", False)) for item in previews
        )
        policy: Literal["block", "unlink", "delete"] = "block"
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Permanently delete photographs")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText(
            "This permanently removes the selected photographs and their related analyses. Items not already in Trash will be moved there automatically."
        )
        dialog.setInformativeText(self._removal_summary(previews))
        cancel = dialog.addButton(QMessageBox.StandardButton.Cancel)
        if dependencies:
            unlink = dialog.addButton(
                "Delete photos, keep observations", QMessageBox.ButtonRole.DestructiveRole
            )
            delete_all = dialog.addButton(
                "Delete photos and observations", QMessageBox.ButtonRole.DestructiveRole
            )
            dialog.setDefaultButton(cancel)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked is unlink:
                policy = "unlink"
            elif clicked is delete_all:
                policy = "delete"
            else:
                return
        else:
            confirm = dialog.addButton("Permanently delete", QMessageBox.ButtonRole.DestructiveRole)
            dialog.setDefaultButton(cancel)
            dialog.exec()
            if dialog.clickedButton() is not confirm:
                return
        self._run_maintenance_operation("delete", selected, observation_policy=policy)

    def selected_asset_ids(self) -> tuple[str, ...]:
        """Return the current visible Library selection by stable public identity."""
        current = tuple(
            str(item.data(Qt.ItemDataRole.UserRole)) for item in self._grid.selectionModel().selectedIndexes()
        )
        return current or self._last_selected_asset_ids

    def select_asset(self, asset_id: str) -> bool:
        """Select and focus a stable asset identity in the photo library."""
        for row, public_id in enumerate(self._gallery_model.public_ids()):
            if str(public_id) == str(asset_id):
                index = self._gallery_model.index(row, 0)
                self._grid.setCurrentIndex(index)
                self._grid.scrollTo(index)
                return True
        return False

    def open_selected_viewer(self) -> None:
        selected = self._grid.selectionModel().selectedIndexes()
        if not selected:
            return
        public_id = str(selected[0].data(Qt.ItemDataRole.UserRole))
        ordered_ids = self._gallery_model.public_ids()
        self.viewer_requested.emit(ordered_ids, public_id)

    @Slot(str, int)
    def _page_failed(self, message: str, request_id: int) -> None:
        if request_id != self._page_request_id:
            return
        self._refreshing = False
        self._failed(message)

    @Slot(str)
    def _failed(self, message: str) -> None:
        self._count.setText(f"Catalog error: {message}")
        self._refresh.setEnabled(True)

    def _track(self, thread: QThread, worker: QObject) -> None:
        # Keep both Python wrappers alive until the Qt thread finishes.  Retaining
        # only the QThread is insufficient: PySide may garbage-collect a local
        # worker before the thread event loop invokes its slot, making Refresh
        # appear to do nothing without producing an error.
        self._threads.add(thread)
        self._workers.add(worker)

        def cleanup() -> None:
            self._workers.discard(worker)
            self._threads.discard(thread)

        thread.finished.connect(cleanup)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
