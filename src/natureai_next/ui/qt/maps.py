"""Lightweight Qt workspace for local OpenStreetMap-compatible MBTiles."""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from natureai_next.application.map_workspace import (
    OfflineMapWorkspaceService,
    lat_to_tile_y,
    lon_to_tile_x,
    package_effective_min_zoom,
    package_is_overview,
    package_viewpoint,
    packages_viewpoint,
    tile_x_to_lon,
    tile_y_to_lat,
    asset_location_label,
)
from natureai_next.application.temporal_map import TemporalMapService
from natureai_next.domain.maps import GpsTrack
from natureai_next.domain.maps import is_nautical_overlay
from natureai_next.domain.temporal_movement import TemporalDisplayMode, TemporalStep, TimeWindow
from natureai_next.ports.gps_tracks import GpsTrackLoader

try:
    from PySide6.QtCore import QDateTime, QRectF, Qt, QTimer, Signal
    from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDateTimeEdit,
        QFileDialog,
        QGraphicsEllipseItem,
        QGraphicsLineItem,
        QGraphicsPixmapItem,
        QGraphicsScene,
        QGraphicsTextItem,
        QGraphicsView,
        QGridLayout,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QMessageBox,
        QPushButton,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


@dataclass(slots=True)
class MapViewState:
    latitude: float = 0.0
    longitude: float = 0.0
    zoom: int = 2


class OfflineMapCanvas(QGraphicsView):
    observation_requested = Signal(str)
    viewport_requested = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setScene(QGraphicsScene(self))
        self.setMinimumSize(640, 480)
        self.setBackgroundBrush(QBrush(QColor("#d8dde3")))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._base_x = 0
        self._base_y = 0
        self._zoom_level = 2
        self._tile_size = 256

    def show_result(
        self,
        service: OfflineMapWorkspaceService,
        state: MapViewState,
        temporal_frame=None,
        gps_track: GpsTrack | None = None,
        package_ids: frozenset[str] | None = None,
    ) -> tuple[str, str]:
        scene = self.scene()
        scene.clear()
        result = service.workspace(
            latitude=state.latitude,
            longitude=state.longitude,
            zoom=state.zoom,
            package_ids=package_ids,
        )
        tile_size = 256
        center_x = lon_to_tile_x(state.longitude, state.zoom)
        center_y = lat_to_tile_y(state.latitude, state.zoom)
        base_x = math.floor(center_x) - 2
        base_y = math.floor(center_y) - 2
        self._base_x = base_x
        self._base_y = base_y
        self._zoom_level = state.zoom
        world_count = 1 << state.zoom
        package = result.package
        used_packages: dict[str, object] = {}
        for row in range(5):
            for column in range(5):
                tile_x = base_x + column
                tile_y = base_y + row
                rect = QRectF(column * tile_size, row * tile_size, tile_size, tile_size)
                if 0 <= tile_y < world_count:
                    wrapped_x = tile_x % world_count
                    tile_latitude = tile_y_to_lat(tile_y + 0.5, state.zoom)
                    tile_longitude = tile_x_to_lon(tile_x + 0.5, state.zoom)
                    selected_package, tile = service.tile_for_coordinate(
                        result.packages,
                        latitude=tile_latitude,
                        longitude=tile_longitude,
                        zoom=state.zoom,
                        x=wrapped_x,
                        y=tile_y,
                    )
                    if tile is not None:
                        if selected_package is not None:
                            used_packages[selected_package.public_id] = selected_package
                        pixmap = QPixmap()
                        pixmap.loadFromData(tile.data)
                        item = QGraphicsPixmapItem(pixmap)
                        item.setPos(rect.x(), rect.y())
                        item.setZValue(-100.0)
                        scene.addItem(item)
                    else:
                        background = scene.addRect(
                            rect, QPen(QColor("#a7adb5")), QBrush(QColor("#eef1f4"))
                        )
                        background.setZValue(-100.0)
                    for overlay_package, overlay_tile in service.overlay_tiles_for_coordinate(
                        result.packages,
                        latitude=tile_latitude,
                        longitude=tile_longitude,
                        zoom=state.zoom,
                        x=wrapped_x,
                        y=tile_y,
                    ):
                        used_packages[overlay_package.public_id] = overlay_package
                        overlay_pixmap = QPixmap()
                        overlay_pixmap.loadFromData(overlay_tile.data)
                        overlay_item = QGraphicsPixmapItem(overlay_pixmap)
                        overlay_item.setPos(rect.x(), rect.y())
                        overlay_item.setZValue(-90.0)
                        scene.addItem(overlay_item)
                else:
                    background = scene.addRect(
                        rect, QPen(QColor("#a7adb5")), QBrush(QColor("#eef1f4"))
                    )
                    background.setZValue(-100.0)

        def marker_position(latitude: float, longitude: float) -> tuple[float, float]:
            x = (lon_to_tile_x(longitude, state.zoom) - base_x) * tile_size
            y = (lat_to_tile_y(latitude, state.zoom) - base_y) * tile_size
            return x, y

        observations = (
            result.observations if temporal_frame is None else temporal_frame.observations
        )
        for observation in observations:
            x, y = marker_position(observation.latitude, observation.longitude)
            marker = QGraphicsEllipseItem(x - 6, y - 6, 12, 12)
            marker.setBrush(QBrush(QColor("#be3a34")))
            marker.setPen(QPen(QColor("white"), 2))
            marker.setToolTip(observation.scientific_name or observation.observation_public_id)
            marker.setData(0, observation.observation_public_id)
            marker.setZValue(40.0)
            scene.addItem(marker)
        for cluster in result.asset_clusters:
            x, y = marker_position(cluster.latitude, cluster.longitude)
            radius = 11 if cluster.total_count < 100 else 14 if cluster.total_count < 1000 else 17
            marker = QGraphicsEllipseItem(x - radius, y - radius, radius * 2, radius * 2)
            marker.setBrush(QBrush(QColor("#2f8f5b")))
            marker.setPen(QPen(QColor("white"), 2))
            marker.setToolTip(
                f"{cluster.label}: {cluster.total_count} media\n"
                f"Photos {cluster.image_count} · Videos {cluster.video_count} · Sounds {cluster.audio_count}\n"
                f"Capture {cluster.capture_count} · Subject {cluster.subject_count} · User-defined {cluster.user_defined_count}"
            )
            marker.setZValue(50.0)
            scene.addItem(marker)
            count = QGraphicsTextItem("999+" if cluster.total_count > 999 else str(cluster.total_count))
            count.setDefaultTextColor(QColor("white"))
            count.setPos(x - radius + 2, y - 10)
            count.setToolTip(marker.toolTip())
            count.setZValue(51.0)
            scene.addItem(count)
        if temporal_frame is not None and temporal_frame.track is not None:
            points = temporal_frame.track.points
            for first, second in itertools.pairwise(points):
                x1, y1 = marker_position(first.latitude, first.longitude)
                x2, y2 = marker_position(second.latitude, second.longitude)
                line = QGraphicsLineItem(x1, y1, x2, y2)
                pen = QPen(QColor("#6f3fb6"), 3)
                if not (first.verified and second.verified):
                    pen.setStyle(Qt.PenStyle.DashLine)
                line.setPen(pen)
                line.setZValue(20.0)
                scene.addItem(line)
        if gps_track is not None:
            for segment in gps_track.segments:
                for first, second in itertools.pairwise(segment):
                    x1, y1 = marker_position(first.latitude, first.longitude)
                    x2, y2 = marker_position(second.latitude, second.longitude)
                    line = QGraphicsLineItem(x1, y1, x2, y2)
                    line.setPen(QPen(QColor("#e07b24"), 3))
                    line.setZValue(20.0)
                    scene.addItem(line)
        for site in result.sites:
            if site.latitude is None or site.longitude is None:
                continue
            x, y = marker_position(site.latitude, site.longitude)
            marker = QGraphicsEllipseItem(x - 5, y - 5, 10, 10)
            marker.setBrush(QBrush(QColor("#285c9d")))
            marker.setPen(QPen(QColor("white"), 2))
            marker.setToolTip(site.name)
            marker.setZValue(30.0)
            scene.addItem(marker)

        if package is None:
            message = (
                "Nautical overlay shown without a basemap"
                if any(is_nautical_overlay(item) for item in used_packages.values())
                else "No enabled offline map package covers this view"
            )
            text = QGraphicsTextItem(message)
            text.setDefaultTextColor(QColor("#333333"))
            text.setPos(18, 18)
            text.setZValue(100.0)
            scene.addItem(text)
        scene.setSceneRect(0, 0, tile_size * 5, tile_size * 5)
        self.fitInView(
            QRectF(tile_size, tile_size, tile_size * 3, tile_size * 3),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        if used_packages:
            attributions: list[str] = []
            urls: list[str] = []
            for selected in used_packages.values():
                if selected.attribution and selected.attribution not in attributions:
                    attributions.append(selected.attribution)
                if selected.attribution_url and selected.attribution_url not in urls:
                    urls.append(selected.attribution_url)
            return " | ".join(attributions), urls[0] if len(urls) == 1 else ""
        return result.attribution, result.attribution_url

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        center = self.mapToScene(self.viewport().rect().center())
        center_x = self._base_x + center.x() / self._tile_size
        center_y = self._base_y + center.y() / self._tile_size
        longitude = tile_x_to_lon(center_x, self._zoom_level)
        latitude = tile_y_to_lat(center_y, self._zoom_level)
        self.viewport_requested.emit(latitude, longitude)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        item = self.itemAt(event.position().toPoint())
        if item is not None:
            public_id = item.data(0)
            if isinstance(public_id, str):
                self.observation_requested.emit(public_id)
                return
        super().mouseDoubleClickEvent(event)


class OfflineMapWorkspace(QWidget):
    """First offline map UI; service creation stays lazy until the workspace opens."""

    observation_requested = Signal(str)

    def __init__(
        self,
        service_factory: Callable[[], OfflineMapWorkspaceService],
        temporal_service_factory: Callable[[], TemporalMapService] | None = None,
        vector_view_factory: Callable[[object, QWidget], QWidget] | None = None,
        gps_track_loader: GpsTrackLoader | None = None,
        project_database_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service_factory = service_factory
        self._temporal_service_factory = temporal_service_factory
        self._temporal_service: TemporalMapService | None = None
        self._service: OfflineMapWorkspaceService | None = None
        self._vector_view_factory = vector_view_factory
        self._vector_view: QWidget | None = None
        self._vector_package_id: str | None = None
        self._gps_track_loader = gps_track_loader
        self._gps_track: GpsTrack | None = None
        self._project_database_path = Path(project_database_path) if project_database_path else None
        self._active_project_id: str | None = None
        self._active_project_feature: dict | None = None
        self._project_area_applied_view = None
        self._state = MapViewState()
        self._updating_areas = False
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        for label, dlat, dlon in (("←", 0, -1), ("↑", 1, 0), ("↓", -1, 0), ("→", 0, 1)):
            button = QPushButton(label)
            button.setToolTip("Pan map")
            button.clicked.connect(lambda _checked=False, a=dlat, b=dlon: self._pan(a, b))
            controls.addWidget(button)
        self._zoom = QComboBox()
        self._zoom.addItems(str(value) for value in range(0, 19))
        self._zoom.setCurrentText("2")
        self._zoom.currentTextChanged.connect(self._set_zoom)
        controls.addWidget(QLabel("Zoom"))
        controls.addWidget(self._zoom)
        self._areas = QComboBox()
        self._areas.setToolTip("Enabled offline map areas")
        self._areas.currentIndexChanged.connect(self._area_changed)
        controls.addWidget(QLabel("Area"))
        controls.addWidget(self._areas)
        self._zoom_to_area = QPushButton("Zoom to Area")
        self._zoom_to_area.clicked.connect(self._zoom_to_selected_area)
        controls.addWidget(self._zoom_to_area)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(lambda: self.refresh(auto_center=True))
        controls.addWidget(refresh)
        self._open_gpx = QPushButton("Open GPX Track…")
        self._open_gpx.setEnabled(gps_track_loader is not None)
        self._open_gpx.clicked.connect(self._open_gpx_track)
        controls.addWidget(self._open_gpx)
        self._clear_gpx = QPushButton("Clear Track")
        self._clear_gpx.setEnabled(False)
        self._clear_gpx.clicked.connect(self._clear_gpx_track)
        controls.addWidget(self._clear_gpx)
        for text, command in (("Draw Project Area", "apertureStartProjectDrawing"), ("Undo Point", "apertureUndoProjectPoint"), ("Finish & Attach…", "apertureFinishProjectDrawing"), ("Clear Area", "apertureClearProjectDrawing")):
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, value=command: self._project_drawing_command(value))
            controls.addWidget(button)
        self._project_snapshot = QPushButton("Save Project Snapshot…")
        self._project_snapshot.clicked.connect(self._save_project_snapshot)
        controls.addWidget(self._project_snapshot)
        controls.addStretch(1)
        layout.addLayout(controls)
        timeline = QGridLayout()
        self._start = QDateTimeEdit(QDateTime.currentDateTime().addYears(-1))
        self._start.setCalendarPopup(True)
        self._end = QDateTimeEdit(QDateTime.currentDateTime())
        self._end.setCalendarPopup(True)
        self._filter_dates = QCheckBox("Filter observations by date")
        self._filter_dates.setChecked(False)
        self._mode = QComboBox()
        self._mode.addItems([mode.value for mode in TemporalDisplayMode])
        self._step = QComboBox()
        self._step.addItems([step.value for step in TemporalStep])
        self._step.setCurrentText(TemporalStep.MONTH.value)
        self._series = QComboBox()
        self._series.setEditable(True)
        self._series.setToolTip("Series public ID required for trail mode")
        self._play = QPushButton("Play")
        self._play.clicked.connect(self._toggle_playback)
        timeline.addWidget(QLabel("From"), 0, 0)
        timeline.addWidget(self._start, 0, 1)
        timeline.addWidget(QLabel("To"), 0, 2)
        timeline.addWidget(self._end, 0, 3)
        timeline.addWidget(QLabel("Mode"), 1, 0)
        timeline.addWidget(self._mode, 1, 1)
        timeline.addWidget(QLabel("Step"), 1, 2)
        timeline.addWidget(self._step, 1, 3)
        timeline.addWidget(QLabel("Series"), 2, 0)
        timeline.addWidget(self._series, 2, 1, 1, 2)
        timeline.addWidget(self._play, 2, 3)
        timeline.addWidget(self._filter_dates, 3, 0, 1, 4)
        self._filter_dates.toggled.connect(self._date_filter_toggled)
        for control in (self._start, self._end, self._mode, self._step, self._series):
            if hasattr(control, "dateTimeChanged"):
                control.dateTimeChanged.connect(self.refresh)
            elif hasattr(control, "currentTextChanged"):
                control.currentTextChanged.connect(self.refresh)
        layout.addLayout(timeline)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._advance_playback)
        self._date_filter_toggled(False)
        self._canvas = OfflineMapCanvas(self)
        self._canvas.observation_requested.connect(self.observation_requested)
        self._canvas.viewport_requested.connect(self._set_viewport_center)
        self._map_stack = QStackedWidget(self)
        self._map_stack.addWidget(self._canvas)
        layout.addWidget(self._map_stack, 1)
        self._status = QLabel("Open the map to activate the optional offline-map database.")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._renderer_status = QLabel("")
        self._renderer_status.setWordWrap(True)
        layout.addWidget(self._renderer_status)
        self._attribution = QLabel("")
        self._attribution.setOpenExternalLinks(True)
        layout.addWidget(self._attribution)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self.refresh(auto_center=True)

    def refresh(self, *, auto_center: bool = False) -> None:
        try:
            if self._service is None:
                self._service = self._service_factory()
            packages = self._refresh_area_selector()
            capabilities = self._service.package_capabilities()
            ready = sum(1 for item in capabilities if item.renderable)
            blocked = [
                item
                for item in capabilities
                if item.package_format in {"vector-mbtiles", "pmtiles"} and not item.renderable
            ]
            if blocked:
                blocker = blocked[0].message
                self._renderer_status.setText(
                    f"Map engine: {ready} package(s) ready; {len(blocked)} valid vector package(s) blocked. {blocker}."
                )
            elif capabilities:
                self._renderer_status.setText(
                    f"Map engine: {ready} installed package(s) ready in the current renderer."
                )
            else:
                self._renderer_status.setText("Map engine: no installed offline map packages.")
            selected_id = self._areas.currentData()
            package_ids = (
                None
                if selected_id == "__all__"
                else frozenset({selected_id})
                if isinstance(selected_id, str)
                else None
            )
            current = self._service.workspace(
                latitude=self._state.latitude,
                longitude=self._state.longitude,
                zoom=self._state.zoom,
                package_ids=package_ids,
            )
            if auto_center and current.package is None and packages:
                if selected_id == "__all__":
                    self._set_state_to_packages(packages)
                elif isinstance(selected_id, str):
                    self._set_state_to_package(self._service.package(selected_id))
                else:
                    self._set_state_to_package(packages[0])
            temporal_frame = None
            base = self._service.workspace(
                latitude=self._state.latitude,
                longitude=self._state.longitude,
                zoom=self._state.zoom,
                package_ids=package_ids,
            )
            if self._temporal_service_factory is not None and self._filter_dates.isChecked():
                if self._temporal_service is None:
                    self._temporal_service = self._temporal_service_factory()
                start_us = self._start.dateTime().toMSecsSinceEpoch() * 1000
                end_us = self._end.dateTime().toMSecsSinceEpoch() * 1000
                window = TimeWindow(start_us, end_us)
                mode = TemporalDisplayMode(self._mode.currentText())
                series = self._series.currentText().strip() or None
                temporal_frame = self._temporal_service.frame(
                    bounds=base.bounds, window=window, display_mode=mode, series_public_id=series
                )
            selected = (
                self._service.package(selected_id)
                if isinstance(selected_id, str) and selected_id != "__all__"
                else None
            )
            vector_packages = (
                tuple(
                    package
                    for package in packages
                    if package.format == "vector-mbtiles"
                    and self._state.zoom >= package_effective_min_zoom(package, composite=True)
                    and (package.max_zoom is None or self._state.zoom <= package.max_zoom)
                )
                if selected_id == "__all__"
                else (selected,)
                if selected is not None and selected.format == "vector-mbtiles"
                else ()
            )
            nautical_overlays = tuple(
                package for package in packages if is_nautical_overlay(package)
            )
            if nautical_overlays:
                self._renderer_status.setText(
                    self._renderer_status.text()
                    + " OpenSeaMap nautical overlay enabled — reference use only; not a certified navigational chart."
                )
            if (
                selected_id == "__all__"
                and self._state.zoom < 9
                and not any(
                    package.format == "vector-mbtiles" and package_is_overview(package)
                    for package in packages
                )
            ):
                self._renderer_status.setText(
                    "Map engine: regional extracts are hidden below zoom 9 to prevent false province mosaics; install a Netherlands overview package for complete country-level coverage."
                )
            if vector_packages and self._vector_view_factory is not None:
                vector_key = "|".join(
                    sorted(
                        package.public_id
                        for package in vector_packages + nautical_overlays
                    )
                )
                if self._vector_view is None or self._vector_package_id != vector_key:
                    if self._vector_view is not None:
                        self._map_stack.removeWidget(self._vector_view)
                        self._vector_view.deleteLater()
                    combined_sources = vector_packages + nautical_overlays
                    vector_source = (
                        combined_sources if len(combined_sources) > 1 else combined_sources[0]
                    )
                    self._vector_view = self._vector_view_factory(vector_source, self)
                    self._project_area_applied_view = None
                    connector = getattr(self._vector_view, "aperture_connect_viewpoint", None)
                    if callable(connector):
                        connector(self._vector_viewpoint_changed)
                    polygon_connector = getattr(self._vector_view, "aperture_connect_project_polygon", None)
                    if callable(polygon_connector):
                        polygon_connector(self._attach_project_polygon)
                    error_connector = getattr(self._vector_view, "aperture_connect_project_error", None)
                    if callable(error_connector):
                        error_connector(lambda message: QMessageBox.information(self, "Project area", message))
                    self._vector_package_id = vector_key
                    self._map_stack.addWidget(self._vector_view)
                self._map_stack.setCurrentWidget(self._vector_view)
                updater = getattr(self._vector_view, "aperture_set_viewpoint", None)
                if callable(updater):
                    updater(self._state.longitude, self._state.latitude, self._state.zoom)
                overlay_updater = getattr(self._vector_view, "aperture_set_overlays", None)
                if callable(overlay_updater):
                    overlay_updater(base, temporal_frame, self._gps_track)
                if self._active_project_feature is not None and self._project_area_applied_view is not self._vector_view:
                    area_updater = getattr(self._vector_view, "aperture_set_project_area", None)
                    if callable(area_updater):
                        area_updater(self._active_project_feature)
                        self._project_area_applied_view = self._vector_view
                attributions = list(
                    dict.fromkeys(
                        package.attribution for package in vector_packages if package.attribution
                    )
                )
                urls = list(
                    dict.fromkeys(
                        package.attribution_url
                        for package in vector_packages
                        if package.attribution_url
                    )
                )
                attribution, url = " | ".join(attributions), urls[0] if len(urls) == 1 else ""
            else:
                self._map_stack.setCurrentWidget(self._canvas)
                attribution, url = self._canvas.show_result(
                    self._service, self._state, temporal_frame, self._gps_track, package_ids
                )
            self._status.setText(
                f"Center {self._state.latitude:.4f}, {self._state.longitude:.4f} • zoom {self._state.zoom}"
            )
            self._attribution.setText(
                f'<a href="{url}">{attribution}</a>' if attribution and url else attribution
            )
        except Exception as exc:  # isolate optional subsystem errors from the desktop shell
            self._status.setText(f"Offline map unavailable: {exc}")
            self._renderer_status.setText("Map engine readiness could not be determined.")
            self._attribution.clear()

    def _refresh_area_selector(self):
        assert self._service is not None
        packages = self._service.available_packages()
        selected = self._areas.currentData()
        self._updating_areas = True
        try:
            self._areas.clear()
            self._areas.addItem("All", "__all__")
            for package in packages:
                if is_nautical_overlay(package):
                    continue
                self._areas.addItem(package.package_name, package.public_id)
            if selected is not None:
                index = self._areas.findData(selected)
                if index >= 0:
                    self._areas.setCurrentIndex(index)
        finally:
            self._updating_areas = False
        self._areas.setEnabled(bool(packages))
        self._zoom_to_area.setEnabled(bool(packages))
        return packages

    def _area_changed(self, _index: int) -> None:
        if not self._updating_areas and self._areas.currentData() is not None:
            self._zoom_to_selected_area()

    def _zoom_to_selected_area(self) -> None:
        if self._service is None:
            self._service = self._service_factory()
        public_id = self._areas.currentData()
        if not isinstance(public_id, str):
            self._status.setText("No enabled offline map area is installed.")
            return
        try:
            if public_id == "__all__":
                packages = self._service.available_packages()
                if not packages:
                    self._status.setText("No enabled offline map area is installed.")
                    return
                self._set_state_to_packages(packages)
            else:
                package = self._service.package(public_id)
                self._set_state_to_package(package)
            self.refresh()
        except Exception as exc:
            self._status.setText(f"Cannot open offline map area: {exc}")

    def _set_state_to_package(self, package) -> None:
        viewpoint = package_viewpoint(package)
        self._state.latitude = viewpoint.latitude
        self._state.longitude = viewpoint.longitude
        self._state.zoom = viewpoint.zoom
        self._zoom.blockSignals(True)
        try:
            self._zoom.setCurrentText(str(viewpoint.zoom))
        finally:
            self._zoom.blockSignals(False)

    def _set_state_to_packages(self, packages) -> None:
        viewpoint = packages_viewpoint(tuple(packages))
        self._state.latitude = viewpoint.latitude
        self._state.longitude = viewpoint.longitude
        self._state.zoom = viewpoint.zoom
        self._zoom.blockSignals(True)
        try:
            self._zoom.setCurrentText(str(viewpoint.zoom))
        finally:
            self._zoom.blockSignals(False)

    def _set_zoom(self, value: str) -> None:
        self._state.zoom = int(value)
        self.refresh()

    def _vector_viewpoint_changed(self, latitude: float, longitude: float, zoom: float) -> None:
        self._state.latitude = max(-85.0, min(85.0, latitude))
        self._state.longitude = ((longitude + 180.0) % 360.0) - 180.0
        self._state.zoom = max(0, min(18, int(round(zoom))))
        self._zoom.blockSignals(True)
        try:
            self._zoom.setCurrentText(str(self._state.zoom))
        finally:
            self._zoom.blockSignals(False)
        QTimer.singleShot(0, self.refresh)

    def _project_drawing_command(self, command: str) -> None:
        if self._vector_view is None or self._map_stack.currentWidget() is not self._vector_view:
            QMessageBox.information(self, "Project map", "Open an installed vector StreetMaps area before drawing a project boundary.")
            return
        self._vector_view.page().runJavaScript(f"if(window.{command})window.{command}();")

    def select_project(self, project_id: str) -> None:
        """Keep Research context while drawing an area or saving a map snapshot."""
        self._active_project_id = str(project_id or "") or None
        self._active_project_feature = None
        self._project_area_applied_view = None
        if self._active_project_id and self._project_database_path is not None:
            from natureai_next.application.project_management import ProjectManagementService
            areas = ProjectManagementService(self._project_database_path).research_areas(self._active_project_id)
            if areas:
                feature = areas[0].get("feature")
                if isinstance(feature, dict):
                    self._active_project_feature = feature
        # Research opens Maps before passing its project identity. Refresh here
        # so the retained GeoJSON is immediately replayed into the live map.
        self.refresh(auto_center=False)

    def _choose_project(self):
        if self._project_database_path is None:
            QMessageBox.warning(self, "Project map", "The Project database is not available.")
            return None
        from natureai_next.application.project_management import ProjectManagementService
        service = ProjectManagementService(self._project_database_path)
        projects = service.projects()
        if not projects:
            QMessageBox.information(self, "Project map", "Create a project first, then return to Maps.")
            return None
        if self._active_project_id:
            selected = next(
                (project for project in projects if project.project_id == self._active_project_id),
                None,
            )
            if selected is not None:
                return service, selected
            self._active_project_id = None
        labels = [f"{project.name} — {project.project_id[:8]}" for project in projects]
        label, accepted = QInputDialog.getItem(self, "Attach to project", "Project", labels, 0, False)
        if not accepted:
            return None
        project = projects[labels.index(label)]
        return service, project

    def _attach_project_polygon(self, feature: dict) -> None:
        chosen = self._choose_project()
        if chosen is None:
            return
        service, project = chosen
        name, accepted = QInputDialog.getText(self, "Project research area", "Area name")
        if not accepted:
            return
        try:
            service.save_research_area(
                project.project_id, name, feature["geometry"]["coordinates"][0], actor_id=project.owner_id
            )
        except Exception as exc:
            QMessageBox.warning(self, "Project research area", str(exc))
            return
        QMessageBox.information(self, "Project research area", f"Boundary attached to {project.name}.")

    def _save_project_snapshot(self) -> None:
        if self._vector_view is None or self._map_stack.currentWidget() is not self._vector_view:
            QMessageBox.information(self, "Project map", "Open an installed vector StreetMaps area before saving a snapshot.")
            return
        chosen = self._choose_project()
        if chosen is None:
            return
        service, project = chosen
        name, accepted = QInputDialog.getText(self, "Project map snapshot", "Snapshot name")
        if not accepted:
            return
        snapshot_root = self._project_database_path.parent / "project-map-snapshots"
        snapshot_root.mkdir(parents=True, exist_ok=True)
        path = snapshot_root / f"{project.project_id}-{QDateTime.currentMSecsSinceEpoch()}.png"
        if not self._vector_view.grab().save(str(path), "PNG"):
            QMessageBox.warning(self, "Project map snapshot", "The visible map could not be rendered to PNG.")
            return
        try:
            service.add_map_snapshot(
                project.project_id, name, path, actor_id=project.owner_id,
                viewport={"latitude": self._state.latitude, "longitude": self._state.longitude, "zoom": self._state.zoom},
            )
        except Exception as exc:
            QMessageBox.warning(self, "Project map snapshot", str(exc))
            return
        QMessageBox.information(self, "Project map snapshot", f"Visible StreetMaps view attached to {project.name}.")

    def _open_gpx_track(self) -> None:
        if self._gps_track_loader is None:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open GPS track", "", "GPX tracks (*.gpx);;All files (*)"
        )
        if not filename:
            return
        try:
            self._gps_track = self._gps_track_loader.load(Path(filename))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "GPS track", str(exc))
            return
        self._clear_gpx.setEnabled(True)
        self._status.setText(
            f"Loaded GPS track {self._gps_track.name} ({self._gps_track.point_count} points)."
        )
        self.refresh()

    def _clear_gpx_track(self) -> None:
        self._gps_track = None
        self._clear_gpx.setEnabled(False)
        self.refresh()

    def _set_viewport_center(self, latitude: float, longitude: float) -> None:
        latitude = max(-85.0, min(85.0, float(latitude)))
        longitude = ((float(longitude) + 180.0) % 360.0) - 180.0
        if (
            abs(latitude - self._state.latitude) < 1e-7
            and abs(longitude - self._state.longitude) < 1e-7
        ):
            return
        self._state.latitude = latitude
        self._state.longitude = longitude
        self.refresh()

    def _pan(self, latitude_direction: int, longitude_direction: int) -> None:
        step = max(0.05, 90.0 / (1 << max(0, self._state.zoom)))
        self._state.latitude = max(
            -85.0, min(85.0, self._state.latitude + latitude_direction * step)
        )
        self._state.longitude = (
            (self._state.longitude + longitude_direction * step + 180.0) % 360.0
        ) - 180.0
        self.refresh()

    def _date_filter_toggled(self, enabled: bool) -> None:
        for control in (self._start, self._end, self._mode, self._step, self._series, self._play):
            control.setEnabled(enabled)
        if not enabled and self._timer.isActive():
            self._timer.stop()
            self._play.setText("Play")
        if self.isVisible():
            self.refresh()

    def _toggle_playback(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._play.setText("Play")
        else:
            self._timer.start()
            self._play.setText("Pause")

    def _advance_playback(self) -> None:
        start = self._start.dateTime()
        end = self._end.dateTime()
        days = {"day": 1, "week": 7, "month": 30, "season": 91, "year": 365}[
            self._step.currentText()
        ]
        self._start.setDateTime(start.addDays(days))
        self._end.setDateTime(end.addDays(days))
        self.refresh()
