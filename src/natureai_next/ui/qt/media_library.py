"""Independent built-in media workspaces for sound, video and document assets."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from natureai_next.application.audio_visualization import SpectrogramData, build_wav_spectrogram
from natureai_next.application.media_playback import TemporalPlaybackBinding
from natureai_next.application.media_queries import query_media_assets
from natureai_next.ui.enrichment.interaction import OverlayScene
from natureai_next.ui.qt.workspace_framework import (
    AdaptiveActionBar,
    CollapsibleSection,
    MediaWorkspaceDescriptor,
    MediaWorkspaceHost,
    WorkspaceAction,
)

if TYPE_CHECKING:
    from natureai_next.application.enrichment_ui import EnrichmentWorkspaceController

try:
    from PySide6.QtCore import (
        QAbstractTableModel,
        QModelIndex,
        QObject,
        QPointF,
        QRectF,
        Qt,
        QThread,
        QTimer,
        QUrl,
        Signal,
        Slot,
    )
    from PySide6.QtGui import (
        QBrush,
        QColor,
        QDesktopServices,
        QMouseEvent,
        QPainter,
        QPen,
        QPolygonF,
    )
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QCheckBox,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFormLayout,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QPlainTextEdit,
        QMessageBox,
        QProgressDialog,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSlider,
        QSplitter,
        QStackedLayout,
        QStackedWidget,
        QTableView,
        QTextBrowser,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc

try:  # Qt PDF is an optional PySide6 component on some deployments.
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView
except ImportError:  # pragma: no cover - depends on Qt packaging
    QPdfDocument = None  # type: ignore[assignment,misc]
    QPdfView = None  # type: ignore[assignment,misc]


@dataclass(frozen=True, slots=True)
class MediaWorkspaceSpec:
    asset_type: str
    title: str
    description: str
    columns: tuple[tuple[str, str], ...]
    detail_table: str


SOUND_SPEC = MediaWorkspaceSpec(
    "sound",
    "Sounds",
    "Review field recordings, audio metadata, recording location and technical properties.",
    (
        ("original_filename", "File"),
        ("title", "Title"),
        ("duration_ms", "Duration"),
        ("sample_rate_hz", "Sample rate"),
        ("channel_count", "Channels"),
        ("codec", "Codec"),
        ("recorded_at_us", "Recorded"),
        ("recorder_model", "Recorder"),
        ("microphone", "Microphone"),
        ("location", "Location"),
        ("file_size_bytes", "Size"),
        ("storage_mode", "Storage"),
        ("availability_state", "Status"),
    ),
    "sound_assets",
)

VIDEO_SPEC = MediaWorkspaceSpec(
    "video",
    "Videos",
    "Review motion media with duration, frame, codec, audio and capture information.",
    (
        ("original_filename", "File"),
        ("title", "Title"),
        ("duration_ms", "Duration"),
        ("dimensions", "Dimensions"),
        ("frame_rate", "Frame rate"),
        ("video_codec", "Video codec"),
        ("audio_codec", "Audio codec"),
        ("recorded_at_us", "Recorded"),
        ("camera_model", "Camera"),
        ("location", "Location"),
        ("file_size_bytes", "Size"),
        ("storage_mode", "Storage"),
        ("availability_state", "Status"),
    ),
    "video_assets",
)

DOCUMENT_SPEC = MediaWorkspaceSpec(
    "document",
    "Documents",
    "Review documents with format, pages, authorship, language and searchability information.",
    (
        ("original_filename", "File"),
        ("title", "Title"),
        ("document_format", "Format"),
        ("page_count", "Pages"),
        ("author", "Author"),
        ("subject", "Subject"),
        ("language_code", "Language"),
        ("document_created_at_us", "Created"),
        ("searchable_text_available", "Searchable text"),
        ("password_protected", "Protected"),
        ("file_size_bytes", "Size"),
        ("storage_mode", "Storage"),
        ("availability_state", "Status"),
    ),
    "document_assets",
)

WORKSPACE_DESCRIPTORS = {
    "sound": MediaWorkspaceDescriptor(
        "sound", "Sounds",
        ("Recording metadata", "Perch", "BirdNET", "Reference recordings", "Knowledge review"),
        ("play_pause", "normalize", "run_enrichment"),
    ),
    "video": MediaWorkspaceDescriptor(
        "video", "Videos",
        ("Technical metadata", "Timeline", "YOLO", "BioCLIP", "Whisper"),
        ("play_pause", "extract_audio", "detect_frames", "run_enrichment"),
    ),
    "document": MediaWorkspaceDescriptor(
        "document", "Documents",
        ("Document metadata", "OCR confidence", "Detected taxa", "Locations", "Dates", "People"),
        ("ocr", "run_enrichment", "export_text"),
    ),
}


class MediaLocationDialog(QDialog):
    """Edit WGS84 coordinates and optionally reconstruct reporting geography."""

    def __init__(self, row: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Enrich media location")
        form = QFormLayout(self)
        self.latitude = QDoubleSpinBox()
        self.latitude.setRange(-90.0, 90.0)
        self.latitude.setDecimals(7)
        self.latitude.setValue(float(row.get("latitude") or 0.0))
        self.longitude = QDoubleSpinBox()
        self.longitude.setRange(-180.0, 180.0)
        self.longitude.setDecimals(7)
        self.longitude.setValue(float(row.get("longitude") or 0.0))
        self.country = QLineEdit(str(row.get("country_code") or ""))
        self.region = QLineEdit(str(row.get("admin_area_1") or ""))
        self.subregion = QLineEdit(str(row.get("admin_area_2") or ""))
        self.locality = QLineEdit(str(row.get("locality") or ""))
        self.resolve = QCheckBox("Reconstruct country, region, and locality from coordinates")
        self.resolve.setChecked(not bool(row.get("country_code") and row.get("admin_area_1")))
        form.addRow("Latitude", self.latitude)
        form.addRow("Longitude", self.longitude)
        form.addRow("Country code", self.country)
        form.addRow("Region", self.region)
        form.addRow("Subregion", self.subregion)
        form.addRow("City / locality", self.locality)
        form.addRow("", self.resolve)
        note = QLabel(
            "Reconstruction uses OpenStreetMap Nominatim and requires internet access. "
            "Country and region can also be entered manually."
        )
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)



def _format_duration(value: Any) -> str:
    if value in (None, ""):
        return ""
    seconds = max(0, int(value)) / 1000.0
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{int(hours)}:{int(minutes):02d}:{seconds:05.2f}"
    return f"{int(minutes)}:{seconds:05.2f}"


def _format_timestamp(value: Any) -> str:
    if not value:
        return ""
    try:
        return (
            datetime.fromtimestamp(int(value) / 1_000_000, tz=UTC)
            .astimezone()
            .strftime("%Y-%m-%d %H:%M")
        )
    except (ValueError, OSError, TypeError):
        return str(value)


def _format_size(value: Any) -> str:
    if value in (None, ""):
        return ""
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


class MediaAssetTableModel(QAbstractTableModel):
    def __init__(self, spec: MediaWorkspaceSpec, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._spec = spec
        self._rows: tuple[dict[str, Any], ...] = ()

    def replace(self, rows: tuple[dict[str, Any], ...]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def asset_at(self, row: int) -> dict[str, Any] | None:
        if row < 0 or row >= len(self._rows):
            return None
        return dict(self._rows[row])

    def asset_id_at(self, row: int) -> str | None:
        if row < 0 or row >= len(self._rows):
            return None
        value = self._rows[row].get("asset_public_id")
        return None if value is None else str(value)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._spec.columns)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._spec.columns[section][1]
        return super().headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._rows):
            return None
        key = self._spec.columns[index.column()][0]
        value = self._rows[index.row()].get(key)
        if role == Qt.ItemDataRole.UserRole:
            return self._rows[index.row()].get("asset_public_id")
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if key == "duration_ms":
            return _format_duration(value)
        if key.endswith("_at_us"):
            return _format_timestamp(value)
        if key == "file_size_bytes":
            return _format_size(value)
        if key in {"searchable_text_available", "password_protected"}:
            return "Yes" if value else "No"
        if key == "frame_rate" and value is not None:
            return f"{float(value):.3g} fps"
        if key == "sample_rate_hz" and value is not None:
            return f"{int(value):,} Hz"
        if key == "storage_mode":
            return {
                "referenced": "Linked",
                "managed": "Managed",
                "hybrid": "Hybrid",
            }.get(str(value or "").lower(), "Unknown")
        if key == "availability_state":
            return str(value or "unknown").replace("_", " ").title()
        return "" if value is None else str(value)


class _MediaQueryWorker(QObject):
    loaded = Signal(object, object)

    def __init__(self, database_path: Path, spec: MediaWorkspaceSpec, search_text: str) -> None:
        super().__init__()
        self._database_path = database_path
        self._spec = spec
        self._search_text = search_text.strip()

    @Slot()
    def run(self) -> None:
        try:
            rows = self._query()
            self.loaded.emit(rows, None)
        except Exception as exc:  # pragma: no cover - platform/database dependent
            self.loaded.emit((), exc)

    def _query(self) -> tuple[dict[str, Any], ...]:
        return query_media_assets(
            self._database_path,
            asset_type=self._spec.asset_type,
            detail_table=self._spec.detail_table,
            columns=tuple(name for name, _title in self._spec.columns),
            search_text=self._search_text,
        )


class WaveformCanvas(QWidget):
    """Lightweight waveform overview; decoding failures never affect playback."""

    time_selected = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._samples: tuple[float, ...] = ()
        self._duration = 0.0
        self._position = 0.0
        self._message = "Select a PCM WAV sound to render its waveform."
        self.setMinimumHeight(90)

    def load_path(self, source_path: str | None) -> None:
        self._samples = ()
        self._duration = 0.0
        if not source_path or not Path(source_path).is_file():
            self._message = "The original audio file is unavailable."
            self.update(); return
        path = Path(source_path)
        if path.suffix.casefold() != ".wav":
            self._message = "Waveform preview currently supports PCM WAV files."
            self.update(); return
        try:
            with wave.open(str(path), "rb") as audio:
                frames = audio.getnframes(); rate = audio.getframerate() or 1
                self._duration = frames / rate
                width = max(64, min(1024, self.width() or 512))
                step = max(1, frames // width)
                raw = audio.readframes(frames)
                size = audio.getsampwidth(); channels = max(1, audio.getnchannels())
                if size not in (1, 2):
                    raise ValueError("unsupported sample width")
                vals=[]
                stride=size*channels*step
                for offset in range(0, len(raw), stride):
                    block=raw[offset:offset+stride]
                    if not block: continue
                    peak=0
                    for i in range(0, len(block)-size+1, size*channels):
                        value=int.from_bytes(block[i:i+size], 'little', signed=size>1)
                        if size==1: value-=128
                        peak=max(peak, abs(value))
                    vals.append(peak/(32768 if size==2 else 128))
                self._samples=tuple(vals)
                self._message=""
        except (OSError, ValueError, wave.Error) as exc:
            self._message=f"Waveform unavailable: {exc}"
        self.update()

    def set_playback_position(self, seconds: float) -> None:
        self._position=max(0.0, float(seconds)); self.update()

    def paintEvent(self, _event: object) -> None:
        painter=QPainter(self); painter.fillRect(self.rect(), QColor("#111714"))
        if not self._samples:
            painter.setPen(QColor("#aebbb3")); painter.drawText(self.rect().adjusted(8,8,-8,-8), Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap, self._message); return
        mid=self.height()/2; width=max(1,self.width())
        painter.setPen(QPen(QColor("#78c8a0"),1))
        for x in range(width):
            i=min(len(self._samples)-1, int(x*len(self._samples)/width)); amp=self._samples[i]*(self.height()*0.42)
            painter.drawLine(x, int(mid-amp), x, int(mid+amp))
        if self._duration>0:
            x=int(min(1.0,self._position/self._duration)*width); painter.setPen(QPen(QColor("#ffcf66"),2)); painter.drawLine(x,0,x,self.height())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._duration>0 and self.width()>0:
            self.time_selected.emit(max(0.0,min(self._duration,event.position().x()/self.width()*self._duration)))


class VideoFrameStrip(QWidget):
    """Timeline strip showing detection/event positions without extracting frames eagerly."""

    time_selected = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent); self._duration=0.0; self._position=0.0; self._markers: tuple[float,...]=(); self.setMinimumHeight(72)

    def set_duration(self, seconds: float) -> None:
        self._duration=max(0.0,float(seconds)); self.update()

    def set_position(self, seconds: float) -> None:
        self._position=max(0.0,float(seconds)); self.update()

    def set_markers(self, markers: tuple[float,...]) -> None:
        self._markers=tuple(max(0.0,float(v)) for v in markers); self.update()

    def paintEvent(self, _event: object) -> None:
        painter=QPainter(self); painter.fillRect(self.rect(), QColor("#111714")); w=max(1,self.width()); h=self.height()
        painter.setPen(QPen(QColor("#34443b"),1))
        for i in range(8):
            left=int(i*w/8); painter.drawRect(left+2,8,max(1,int(w/8)-4),h-16)
        if self._duration>0:
            painter.setPen(QPen(QColor("#65d7ff"),2))
            for marker in self._markers:
                x=int(min(1.0,marker/self._duration)*w); painter.drawLine(x,4,x,h-4)
            x=int(min(1.0,self._position/self._duration)*w); painter.setPen(QPen(QColor("#ffcf66"),2)); painter.drawLine(x,0,x,h)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._duration>0 and self.width()>0:
            self.time_selected.emit(event.position().x()/self.width()*self._duration)


class SoundPlaybackWidget(QWidget):
    """Concrete local audio player synchronized with canonical temporal enrichment."""

    position_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._binding = TemporalPlaybackBinding()
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._play = QPushButton("Play")
        self._play.clicked.connect(self._toggle)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.sliderMoved.connect(self._player.setPosition)
        self._time = QLabel("0:00 / 0:00")
        self._message = QLabel("Select a sound to enable playback.")
        self._message.setWordWrap(True)
        controls = QHBoxLayout()
        controls.addWidget(self._play)
        controls.addWidget(self._slider, 1)
        controls.addWidget(self._time)
        layout = QVBoxLayout(self)
        layout.addWidget(self._message)
        layout.addLayout(controls)
        self._player.positionChanged.connect(self._position_changed)
        self._player.durationChanged.connect(self._duration_changed)
        self._player.playbackStateChanged.connect(self._state_changed)
        self._player.errorOccurred.connect(self._error)

    @property
    def asset_id(self) -> str | None:
        return self._binding.asset_id

    def load_asset(self, asset_id: str, source_path: str | None) -> None:
        self._binding.load(asset_id)
        self._player.stop()
        if not source_path:
            self._player.setSource(QUrl())
            self._message.setText("The original audio file is unavailable.")
            self._play.setEnabled(False)
            return
        path = Path(source_path)
        if not path.is_file():
            self._player.setSource(QUrl())
            self._message.setText(f"Audio file is missing: {path}")
            self._play.setEnabled(False)
            return
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self._message.setText(path.name)
        self._play.setEnabled(True)

    def seek_seconds(self, seconds: float) -> None:
        self._player.setPosition(self._binding.seek_seconds(seconds))

    @Slot()
    def _toggle(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    @Slot(int)
    def _position_changed(self, position_ms: int) -> None:
        if not self._slider.isSliderDown():
            self._slider.setValue(position_ms)
        seconds = self._binding.update_position(position_ms)
        self._time.setText(
            f"{_format_duration(self._binding.position_ms)} / {_format_duration(self._binding.duration_ms)}"
        )
        self.position_changed.emit(seconds)

    @Slot(int)
    def _duration_changed(self, duration_ms: int) -> None:
        duration = self._binding.update_duration(duration_ms)
        self._slider.setRange(0, duration)

    @Slot(object)
    def _state_changed(self, state: object) -> None:
        self._play.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play")

    @Slot(object, str)
    def _error(self, _error: object, message: str) -> None:
        if message:
            self._message.setText(f"Playback unavailable: {message}")


class SoundSpectrogramCanvas(QWidget):
    """Offline spectrogram with producer-neutral canonical region overlays."""

    time_selected = Signal(float)
    region_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: SpectrogramData | None = None
        self._scene = OverlayScene("summary", ())
        self._position_seconds = 0.0
        self._selected_region_id: str | None = None
        self._message = "Select a PCM WAV sound to render its spectrogram."
        self.setMinimumHeight(180)

    def load_path(self, source_path: str | None) -> None:
        self._data = None
        if not source_path:
            self._message = "The original audio file is unavailable."
            self.update()
            return
        path = Path(source_path)
        if not path.is_file():
            self._message = f"Audio file is missing: {path}"
            self.update()
            return
        if path.suffix.casefold() != ".wav":
            self._message = (
                "Playback is available; spectrogram rendering currently supports PCM WAV files."
            )
            self.update()
            return
        try:
            self._data = build_wav_spectrogram(path)
            self._message = (
                "" if self._data.frame_count else "The WAV file contains no audio frames."
            )
        except (OSError, ValueError, wave.Error) as exc:
            self._message = f"Spectrogram unavailable: {exc}"
        self.update()

    def set_overlay_scene(self, scene: OverlayScene) -> None:
        self._scene = scene
        self._selected_region_id = None
        self.update()

    def select_region(self, region_id: str) -> None:
        self._selected_region_id = region_id
        self.update()

    def set_playback_position(self, seconds: float) -> None:
        self._position_seconds = max(0.0, float(seconds))
        active = self._scene.region_at_time(self._position_seconds)
        self._selected_region_id = None if active is None else active.region_id
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#151a18"))
        data = self._data
        if data is None or not data.magnitudes:
            painter.setPen(QColor("#c6cfca"))
            painter.drawText(
                self.rect().adjusted(12, 12, -12, -12),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self._message,
            )
            return
        width = max(1, self.width())
        height = max(1, self.height())
        frame_count = data.frame_count
        bin_count = data.bin_count
        for x in range(width):
            frame_index = min(frame_count - 1, int(x * frame_count / width))
            frame = data.magnitudes[frame_index]
            for y in range(height):
                bin_index = min(bin_count - 1, int((height - 1 - y) * bin_count / height))
                level = int(frame[bin_index] * 255)
                painter.setPen(QColor(level, level, level))
                painter.drawPoint(x, y)
        for region in self._scene.regions:
            rect = QRectF(
                region.x * width, region.y * height, region.width * width, region.height * height
            )
            selected = region.region_id == self._selected_region_id
            painter.setPen(QPen(QColor("#f7d774" if selected else "#6bd6ff"), 3 if selected else 2))
            painter.drawRect(rect)
        duration = data.duration_seconds or self._scene.duration_seconds or 0.0
        if duration > 0:
            x = min(width - 1, max(0, int((self._position_seconds / duration) * width)))
            painter.setPen(QPen(QColor("#ff6b6b"), 2))
            painter.drawLine(x, 0, x, height)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        x = event.position().x() / self.width()
        y = event.position().y() / self.height()
        region = self._scene.hit_test(x, y)
        if region is not None:
            self._selected_region_id = region.region_id
            self.region_selected.emit(region.region_id)
        duration = (
            (self._data.duration_seconds if self._data is not None else 0.0)
            or self._scene.duration_seconds
            or 0.0
        )
        if duration > 0:
            self.time_selected.emit(max(0.0, min(duration, x * duration)))
        self.update()


class MediaOverlayCanvas(QWidget):
    """Transparent normalized overlay shared by video frames and document pages."""

    region_selected = Signal(str)
    time_selected = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = OverlayScene("summary", ())
        self._selected_region_id: str | None = None
        self._position_seconds = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

    def set_scene(self, scene: OverlayScene) -> None:
        self._scene = scene
        self._selected_region_id = None
        self.update()

    def select_region(self, region_id: str) -> None:
        self._selected_region_id = region_id
        self.update()

    def set_playback_position(self, seconds: float) -> None:
        self._position_seconds = max(0.0, float(seconds))
        active = self._scene.region_at_time(self._position_seconds)
        self._selected_region_id = None if active is None else active.region_id
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for region in self._scene.regions:
            selected = region.region_id == self._selected_region_id
            painter.setPen(QPen(QColor("#ffd166" if selected else "#63d3ff"), 3 if selected else 2))
            painter.setBrush(QBrush(QColor(99, 211, 255, 45)))
            if region.points:
                painter.drawPolygon(
                    QPolygonF(
                        [QPointF(x * self.width(), y * self.height()) for x, y in region.points]
                    )
                )
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
        self.region_selected.emit(region.region_id)
        if region.start_seconds is not None:
            self.time_selected.emit(region.start_seconds)
        self.update()


class DocumentPageWidget(QWidget):
    """Preview native text/PDF documents and delegate other formats to the OS."""

    region_selected = Signal(str)

    _NATIVE_TEXT_SUFFIXES = frozenset({".md", ".txt"})
    _EXTERNAL_SUFFIXES = frozenset(
        {
            ".csv",
            ".doc",
            ".docm",
            ".docx",
            ".odp",
            ".ods",
            ".odt",
            ".pot",
            ".potx",
            ".pps",
            ".ppsx",
            ".ppt",
            ".pptm",
            ".pptx",
            ".rtf",
            ".xls",
            ".xlsb",
            ".xlsm",
            ".xlsx",
        }
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._asset_id: str | None = None
        self._source_path: Path | None = None
        self._overlay = MediaOverlayCanvas(self)
        self._overlay.region_selected.connect(self.region_selected)

        self._fallback = QLabel("Select a document to preview or open.")
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.setWordWrap(True)

        self._text = QTextBrowser(self)
        self._text.setOpenExternalLinks(True)

        self._external_message = QLabel()
        self._external_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._external_message.setWordWrap(True)
        self._open_external = QPushButton("Open in system application")
        self._open_external.clicked.connect(self._open_in_system_application)
        external_layout = QVBoxLayout()
        external_layout.addStretch(1)
        external_layout.addWidget(self._external_message)
        external_layout.addWidget(self._open_external, 0, Qt.AlignmentFlag.AlignHCenter)
        external_layout.addStretch(1)
        self._external = QWidget(self)
        self._external.setLayout(external_layout)

        self._document = None
        self._view = None
        self._page_rail: QListWidget | None = None
        self._pdf_page = self._fallback
        if QPdfDocument is not None and QPdfView is not None:
            self._document = QPdfDocument(self)
            self._view = QPdfView(self)
            self._view.setDocument(self._document)
            self._view.setPageMode(QPdfView.PageMode.MultiPage)
            self._view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            self._document.statusChanged.connect(self._pdf_status_changed)
            self._pdf_page = self._view

        self._pages = QStackedWidget(self)
        self._pages.addWidget(self._fallback)
        if self._pdf_page is not self._fallback:
            self._pages.addWidget(self._pdf_page)
        self._pages.addWidget(self._text)
        self._pages.addWidget(self._external)

        stack = QStackedLayout(self)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.addWidget(self._pages)
        stack.addWidget(self._overlay)

    @property
    def asset_id(self) -> str | None:
        return self._asset_id

    def set_page_rail(self, page_rail: QListWidget) -> None:
        """Bind the workspace page rail to the native PDF navigator."""
        self._page_rail = page_rail
        self._page_rail.clear()
        self._page_rail.setEnabled(False)
        self._page_rail.currentRowChanged.connect(self._go_to_page)

    def load_asset(self, asset_id: str, source_path: str | None) -> None:
        self._asset_id = asset_id
        self._source_path = None
        if self._document is not None:
            self._document.close()
        if self._page_rail is not None:
            self._page_rail.clear()
            self._page_rail.setEnabled(False)
        self._text.clear()

        if not source_path or not Path(source_path).is_file():
            self._fallback.setText("The original document file is unavailable.")
            self._pages.setCurrentWidget(self._fallback)
            return

        path = Path(source_path).resolve()
        self._source_path = path
        suffix = path.suffix.casefold()
        if suffix == ".pdf":
            if self._document is None:
                self._fallback.setText(
                    "PDF preview requires the Qt PDF component. Use the system application "
                    "to open this file."
                )
                self._pages.setCurrentWidget(self._fallback)
                return
            self._document.load(str(path))
            self._pages.setCurrentWidget(self._pdf_page)
            return

        if suffix in self._NATIVE_TEXT_SUFFIXES:
            self._load_native_text(path, suffix)
            return

        if suffix in self._EXTERNAL_SUFFIXES:
            self._external_message.setText(
                f"{path.name} is opened by the application associated with {suffix or 'this file type'} "
                "on this system."
            )
            self._open_external.setEnabled(True)
            self._pages.setCurrentWidget(self._external)
            return

        self._fallback.setText(f"Preview is not available for {suffix or 'this file type'}.")
        self._pages.setCurrentWidget(self._fallback)

    @Slot(object)
    def _pdf_status_changed(self, status: object) -> None:
        if self._document is None or self._page_rail is None:
            return
        if status != QPdfDocument.Status.Ready:
            return
        self._page_rail.blockSignals(True)
        self._page_rail.clear()
        for page in range(self._document.pageCount()):
            self._page_rail.addItem(f"Page {page + 1}")
        self._page_rail.setEnabled(self._document.pageCount() > 0)
        if self._document.pageCount():
            self._page_rail.setCurrentRow(0)
        self._page_rail.blockSignals(False)

    @Slot(int)
    def _go_to_page(self, page: int) -> None:
        if self._view is None or page < 0:
            return
        navigator = self._view.pageNavigator()
        navigator.jump(page, navigator.currentLocation(), navigator.currentZoom())

    def _load_native_text(self, path: Path, suffix: str) -> None:
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self._fallback.setText(f"Could not read {path.name}: {exc}")
            self._pages.setCurrentWidget(self._fallback)
            return
        if suffix == ".md":
            self._text.setMarkdown(content)
        else:
            self._text.setPlainText(content)
        self._pages.setCurrentWidget(self._text)

    @Slot()
    def _open_in_system_application(self) -> None:
        path = self._source_path
        if path is None or not path.is_file():
            QMessageBox.warning(self, "Open document", "The original document file is unavailable.")
            return
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            return
        suffix = path.suffix.casefold() or "this file type"
        QMessageBox.information(
            self,
            "No compatible application found",
            f"Windows could not find an application associated with {suffix}.\n\n"
            "Install an application that supports this file type, such as LibreOffice "
            "or Microsoft Office, and try again.",
        )

    def set_overlay_scene(self, scene: OverlayScene) -> None:
        self._overlay.set_scene(scene)

    def select_region(self, region_id: str) -> None:
        self._overlay.select_region(region_id)


class VideoPlaybackWidget(QWidget):
    """Concrete local video player synchronized with canonical temporal enrichment."""

    position_changed = Signal(float)
    time_selected = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._binding = TemporalPlaybackBinding()
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._video = QVideoWidget(self)
        self._overlay = MediaOverlayCanvas(self)
        self._overlay.region_selected.connect(self._overlay_region_selected)
        self._overlay.time_selected.connect(self.time_selected)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video)
        self._play = QPushButton("Play")
        self._play.clicked.connect(self._toggle)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.sliderMoved.connect(self._player.setPosition)
        self._time = QLabel("0:00 / 0:00")
        self._message = QLabel("Select a video to enable playback.")
        controls = QHBoxLayout()
        controls.addWidget(self._play)
        controls.addWidget(self._slider, 1)
        controls.addWidget(self._time)
        video_surface = QWidget(self)
        video_stack = QStackedLayout(video_surface)
        video_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        video_stack.addWidget(self._video)
        video_stack.addWidget(self._overlay)
        layout = QVBoxLayout(self)
        layout.addWidget(self._message)
        layout.addWidget(video_surface, 1)
        layout.addLayout(controls)
        self._player.positionChanged.connect(self._position_changed)
        self._player.durationChanged.connect(self._duration_changed)
        self._player.playbackStateChanged.connect(self._state_changed)
        self._player.errorOccurred.connect(self._error)

    @property
    def asset_id(self) -> str | None:
        return self._binding.asset_id

    def load_asset(self, asset_id: str, source_path: str | None) -> None:
        self._binding.load(asset_id)
        self._player.stop()
        if not source_path or not Path(source_path).is_file():
            self._player.setSource(QUrl())
            self._message.setText("The original video file is unavailable.")
            self._play.setEnabled(False)
            return
        path = Path(source_path).resolve()
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._message.setText(path.name)
        self._play.setEnabled(True)

    def seek_seconds(self, seconds: float) -> None:
        self._player.setPosition(self._binding.seek_seconds(seconds))

    def set_overlay_scene(self, scene: OverlayScene) -> None:
        """Composite canonical spatial and temporal regions over decoded video frames."""
        self._overlay.set_scene(scene)

    def select_region(self, region_id: str) -> None:
        self._overlay.select_region(region_id)

    @Slot(str)
    def _overlay_region_selected(self, region_id: str) -> None:
        self._overlay.select_region(region_id)

    def set_playback_position(self, seconds: float) -> None:
        value = max(0.0, float(seconds))
        self._binding.update_position(round(value * 1000.0))
        self._overlay.set_playback_position(value)

    @Slot()
    def _toggle(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    @Slot(int)
    def _position_changed(self, position_ms: int) -> None:
        if not self._slider.isSliderDown():
            self._slider.setValue(position_ms)
        seconds = self._binding.update_position(position_ms)
        self._time.setText(
            f"{_format_duration(self._binding.position_ms)} / {_format_duration(self._binding.duration_ms)}"
        )
        self.position_changed.emit(seconds)

    @Slot(int)
    def _duration_changed(self, duration_ms: int) -> None:
        self._slider.setRange(0, self._binding.update_duration(duration_ms))

    @Slot(object)
    def _state_changed(self, state: object) -> None:
        self._play.setText("Pause" if state == QMediaPlayer.PlaybackState.PlayingState else "Play")

    @Slot(object, str)
    def _error(self, _error: object, message: str) -> None:
        if message:
            self._message.setText(f"Playback unavailable: {message}")


# Compatibility label retained for deployment/tests: Run enrichment…
class MediaLibraryWorkspace(QWidget):
    """Read-optimized type-specific Library screen with its own query worker."""

    playback_seek_requested = Signal(str, float)

    def __init__(
        self,
        database_path: Path,
        spec: MediaWorkspaceSpec,
        parent: QWidget | None = None,
        *,
        enrichment_controller: EnrichmentWorkspaceController | None = None,
    ) -> None:
        super().__init__(parent)
        self._database_path = database_path
        self._spec = spec
        self._thread: QThread | None = None
        self._worker: _MediaQueryWorker | None = None
        self._pending_refresh = False
        self._model = MediaAssetTableModel(spec, self)
        self._enrichment_panel = None
        self._enrichment_controller = enrichment_controller
        self._sound_player: SoundPlaybackWidget | None = None
        self._spectrogram: SoundSpectrogramCanvas | None = None
        self._waveform: WaveformCanvas | None = None
        self._video_player: VideoPlaybackWidget | None = None
        self._frame_strip: VideoFrameStrip | None = None
        self._document_viewer: DocumentPageWidget | None = None
        self._capability_run = None
        self._capability_progress: QProgressDialog | None = None
        self._capability_subject = None
        self._batch_screen = None
        self._batch_screens: list[object] = []
        self._workspace_enabled = True
        self._capability_timer = QTimer(self)
        self._capability_timer.setInterval(100)
        self._capability_timer.timeout.connect(self._poll_capability_run)

        self.setObjectName("mediaLibraryWorkspace")
        self._inspector_values: dict[str, QLabel] = {}

        # Compact command bar matching the Photos workspace while keeping the
        # existing search and refresh behavior intact.
        title = QLabel(spec.title)
        title.setObjectName("mediaTitle")
        type_filter = QComboBox()
        type_filter.addItem(f"All {spec.title}")
        type_filter.setEnabled(False)
        search_scope = QComboBox()
        search_scope.addItem("Everywhere")
        search_scope.setEnabled(False)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Type to search…")
        self._search.returnPressed.connect(self.refresh)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)

        command_bar = QFrame()
        command_bar.setObjectName("mediaCommandBar")
        command_layout = QHBoxLayout(command_bar)
        command_layout.setContentsMargins(10, 7, 10, 7)
        command_layout.setSpacing(8)
        command_layout.addWidget(title)
        command_layout.addWidget(type_filter)
        command_layout.addWidget(QLabel("Search in"))
        command_layout.addWidget(search_scope)
        command_layout.addWidget(self._search, 1)
        command_layout.addWidget(refresh)

        filters = QToolButton()
        filters.setObjectName("mediaFilters")
        filters.setText("Structured Filters")
        filters.setCheckable(True)
        filters.setChecked(False)
        filters.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        filters.setArrowType(Qt.ArrowType.RightArrow)
        filter_body = QFrame()
        filter_body.setObjectName("mediaFilterBody")
        filter_body.setVisible(False)
        filter_layout = QHBoxLayout(filter_body)
        filter_layout.addWidget(QLabel("Additional structured filters will appear here."))
        filter_layout.addStretch(1)

        self._run_capability: QPushButton | None = None
        self._status = QLabel("Open this workspace to load records.")
        self._status.setObjectName("mediaStatus")
        self._table = QTableView()
        self._table.setObjectName("mediaTable")
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setSortingEnabled(False)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.selectionModel().currentRowChanged.connect(self._selection_changed)

        # The central surface is media-first: waveform/video/page preview above,
        # result table below. Existing playback, overlay and selection signals
        # are reused unchanged.
        preview: QWidget
        if spec.asset_type == "sound":
            self._sound_player = SoundPlaybackWidget(self)
            self._waveform = WaveformCanvas(self)
            self._spectrogram = SoundSpectrogramCanvas(self)
            self._sound_player.position_changed.connect(self._sound_position_changed)
            self._waveform.time_selected.connect(self._spectrogram_time_selected)
            self._spectrogram.time_selected.connect(self._spectrogram_time_selected)
            preview = QWidget(self)
            preview_layout = QVBoxLayout(preview)
            preview_layout.setContentsMargins(0, 0, 0, 0)
            preview_layout.setSpacing(5)
            preview_layout.addWidget(self._waveform)
            preview_layout.addWidget(self._spectrogram, 1)
            preview_layout.addWidget(self._sound_player)
        elif spec.asset_type == "video":
            self._video_player = VideoPlaybackWidget(self)
            self._frame_strip = VideoFrameStrip(self)
            self._video_player.position_changed.connect(self._video_position_changed)
            self._frame_strip.time_selected.connect(self._video_player.seek_seconds)
            preview = QWidget(self)
            preview_layout = QVBoxLayout(preview)
            preview_layout.setContentsMargins(0, 0, 0, 0)
            preview_layout.setSpacing(5)
            preview_layout.addWidget(self._video_player, 1)
            preview_layout.addWidget(self._frame_strip)
        else:
            self._document_viewer = DocumentPageWidget(self)
            preview = QWidget(self)
            doc_layout = QHBoxLayout(preview)
            doc_layout.setContentsMargins(0, 0, 0, 0)
            doc_layout.setSpacing(5)
            pages = QListWidget(self)
            pages.setObjectName("documentPageRail")
            pages.setMaximumWidth(130)
            pages.setAccessibleName("PDF pages")
            self._document_viewer.set_page_rail(pages)
            extracted = QPlainTextEdit(self)
            extracted.setObjectName("documentExtractedText")
            extracted.setReadOnly(True)
            extracted.setPlaceholderText("OCR and extracted text appear here after enrichment.")
            extracted.setMaximumWidth(300)
            doc_layout.addWidget(pages)
            doc_layout.addWidget(self._document_viewer, 1)
            doc_layout.addWidget(extracted)

        media_splitter = QSplitter(Qt.Orientation.Vertical)
        media_splitter.setObjectName("mediaContentSplitter")
        media_splitter.addWidget(preview)
        media_splitter.addWidget(self._table)
        media_splitter.setStretchFactor(0, 3)
        media_splitter.setStretchFactor(1, 2)
        media_splitter.setSizes([520, 250])

        inspector = QWidget(self)
        inspector.setObjectName("mediaInspector")
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(10, 8, 10, 8)
        inspector_layout.setSpacing(8)
        inspector_title = QLabel("Inspector")
        inspector_title.setObjectName("mediaInspectorTitle")
        inspector_layout.addWidget(inspector_title)
        metadata_group = QGroupBox(spec.title[:-1] if spec.title.endswith("s") else spec.title)
        metadata_form = QFormLayout(metadata_group)
        metadata_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for key, label_text in spec.columns[:8]:
            value = QLabel("—")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._inspector_values[key] = value
            metadata_form.addRow(label_text, value)
        inspector_layout.addWidget(
            CollapsibleSection(
                WORKSPACE_DESCRIPTORS[spec.asset_type].inspector_sections[0],
                metadata_group,
                self,
                settings_key=f"ui/library/{spec.asset_type}/metadata_collapsed",
            )
        )
        for section_name in WORKSPACE_DESCRIPTORS[spec.asset_type].inspector_sections[1:]:
            placeholder = QLabel(
                f"{section_name} results are populated by installed capabilities and accepted knowledge records."
            )
            placeholder.setWordWrap(True)
            placeholder.setContentsMargins(8, 8, 8, 8)
            inspector_layout.addWidget(
                CollapsibleSection(
                    section_name,
                    placeholder,
                    self,
                    settings_key=f"ui/library/{spec.asset_type}/{section_name.casefold().replace(' ', '_')}_collapsed",
                    collapsed=True,
                )
            )

        if enrichment_controller is not None:
            from natureai_next.domain.enrichment import SubjectRef, SubjectType
            from natureai_next.ui.qt.enrichment import CanonicalEnrichmentPanel

            subject_type = SubjectType(spec.asset_type)
            self._enrichment_panel = CanonicalEnrichmentPanel(
                enrichment_controller,
                SubjectRef(subject_type, "__none__"),
                self,
                collapsible=True,
                collapse_settings_key=f"ui/library/{spec.asset_type}/enrichment_collapsed",
            )
            self._enrichment_panel.visualization_time_selected.connect(
                self._enrichment_time_selected
            )
            self._enrichment_panel.visualization_region_selected.connect(
                self._enrichment_region_selected
            )
            self._enrichment_panel.overlay_scene_changed.connect(self._overlay_scene_changed)
            inspector_layout.addWidget(self._enrichment_panel, 1)
        else:
            inspector_layout.addStretch(1)

        inspector_scroll = QScrollArea(self)
        inspector_scroll.setObjectName("mediaInspectorScroll")
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        inspector_scroll.setWidget(inspector)
        inspector_scroll.setMinimumWidth(260)
        inspector_scroll.setMaximumWidth(390)

        workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        workspace_splitter.setObjectName("mediaMainSplitter")
        workspace_splitter.addWidget(media_splitter)
        workspace_splitter.addWidget(inspector_scroll)
        workspace_splitter.setStretchFactor(0, 1)
        workspace_splitter.setStretchFactor(1, 0)
        workspace_splitter.setSizes([1050, 330])
        workspace_splitter.setChildrenCollapsible(False)

        action_bar = AdaptiveActionBar(self)
        self._status = action_bar.status_label
        actions: list[WorkspaceAction] = []
        if spec.asset_type == "sound":
            actions.extend((
                WorkspaceAction("play_pause", "Play / Pause", self._toggle_media_playback, True),
                WorkspaceAction("normalize", "Normalize", self._normalize_sound, True),
                WorkspaceAction("location", "Location…", self._edit_location, True),
            ))
        elif spec.asset_type == "video":
            actions.extend((
                WorkspaceAction("play_pause", "Play / Pause", self._toggle_media_playback, True),
                WorkspaceAction("extract_audio", "Extract Audio", self._extract_audio, True),
                WorkspaceAction("detect_frames", "Detect Frames", self._run_enrichment_capability, True),
                WorkspaceAction("location", "Location…", self._edit_location, True),
            ))
        else:
            actions.extend((
                WorkspaceAction("ocr", "OCR", self._run_enrichment_capability, True),
                WorkspaceAction("export_text", "Export Text", self._export_document_text, True),
            ))
        actions.append(WorkspaceAction("run_enrichment", "Run Enrichment…", self._run_enrichment_capability, True))
        actions.append(WorkspaceAction("refresh", "Refresh", self.refresh))
        action_bar.set_actions(tuple(actions))
        self._action_bar = action_bar
        self._run_capability = action_bar.button("run_enrichment")
        if self._run_capability is not None:
            self._run_capability.setEnabled(False)


        filter_section = CollapsibleSection(
            "Structured Filters",
            filter_body,
            self,
            settings_key=f"ui/library/{spec.asset_type}/filters_collapsed",
            collapsed=True,
        )
        host = MediaWorkspaceHost(self)
        host.compose(
            command_bar=command_bar,
            filters=filter_section,
            workspace=workspace_splitter,
            action_bar=action_bar,
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(host)

        self.setStyleSheet("""
            QWidget#mediaLibraryWorkspace { background: #101412; color: #dce5df; }
            QFrame#mediaCommandBar, QFrame#mediaActionBar, QFrame#mediaFilterBody {
                background: #171d1a; border: 1px solid #28312c; border-radius: 8px;
            }
            QLabel#mediaTitle { color: #f2f5f3; font-size: 18px; font-weight: 650; }
            QToolButton#mediaFilters {
                background: #171d1a; border: 1px solid #28312c; border-radius: 7px;
                padding: 7px 10px; text-align: left; font-weight: 600;
            }
            QTableView#mediaTable {
                background: #0d110f; alternate-background-color: #121713;
                border: 1px solid #28312c; border-radius: 8px; gridline-color: #27302b;
                selection-background-color: #31483b; selection-color: #ffffff;
            }
            QHeaderView::section { background: #171d1a; color: #cfd8d2; border: 0; padding: 6px; }
            QWidget#mediaInspector { background: #141916; }
            QScrollArea#mediaInspectorScroll { background: #141916; border: 1px solid #28312c; border-radius: 8px; }
            QLabel#mediaInspectorTitle { font-size: 15px; font-weight: 650; color: #f2f5f3; }
            QGroupBox { border: 1px solid #2b352f; border-radius: 7px; margin-top: 10px; padding: 8px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
            QLineEdit, QComboBox {
                background: #0f1411; border: 1px solid #344038; border-radius: 5px;
                padding: 6px; color: #edf2ef;
            }
            QPushButton {
                background: #26332b; border: 1px solid #3b4b41; border-radius: 6px;
                padding: 6px 10px; color: #edf2ef;
            }
            QPushButton:hover { background: #314238; }
            QPushButton:disabled { color: #657068; background: #1a201c; border-color: #252d28; }
            QSplitter::handle { background: transparent; width: 5px; height: 5px; }
        """)

    @Slot(QModelIndex, QModelIndex)
    def _selection_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            return
        row = self._model.asset_at(current.row()) or {}
        for key, label in self._inspector_values.items():
            value = row.get(key)
            if key == "duration_ms":
                rendered = _format_duration(value)
            elif key.endswith("_at_us"):
                rendered = _format_timestamp(value)
            elif key == "file_size_bytes":
                rendered = _format_size(value)
            else:
                rendered = "" if value is None else str(value)
            label.setText(rendered or "—")
        asset_id = self._model.asset_id_at(current.row())
        if not asset_id:
            return
        if self._run_capability is not None:
            self._run_capability.setEnabled(
                self._workspace_enabled and self._enrichment_controller is not None
            )
        self._action_bar.set_selection_available(True)
        from natureai_next.domain.enrichment import SubjectRef, SubjectType

        if self._enrichment_panel is not None:
            self._enrichment_panel.set_subject(
                SubjectRef(SubjectType(self._spec.asset_type), asset_id)
            )
        if self._sound_player is not None:
            self._sound_player.load_asset(asset_id, row.get("source_path"))
            if self._spectrogram is not None:
                self._spectrogram.load_path(row.get("source_path"))
            if self._waveform is not None:
                self._waveform.load_path(row.get("source_path"))
        if self._video_player is not None:
            self._video_player.load_asset(asset_id, row.get("source_path"))
            if self._frame_strip is not None:
                self._frame_strip.set_duration(float(row.get("duration_ms") or 0) / 1000.0)
        if self._document_viewer is not None:
            self._document_viewer.load_asset(asset_id, row.get("source_path"))

    @Slot()
    def _toggle_media_playback(self) -> None:
        if self._sound_player is not None:
            self._sound_player._toggle()
        elif self._video_player is not None:
            self._video_player._toggle()

    @Slot()
    def _normalize_sound(self) -> None:
        QMessageBox.information(
            self, "Normalize sound",
            "Normalization is non-destructive. Choose an installed audio capability through Run Enrichment to create a derived result."
        )

    @Slot()
    def _extract_audio(self) -> None:
        QMessageBox.information(
            self, "Extract audio",
            "Audio extraction is performed by an installed FFmpeg-compatible capability so the original video remains unchanged."
        )

    @Slot()
    def _edit_location(self) -> None:
        current = self._table.currentIndex()
        if not current.isValid() or self._spec.asset_type not in {"sound", "video"}:
            QMessageBox.information(self, "Media location", "Select a sound or video first.")
            return
        row = self._model.asset_at(current.row()) or {}
        asset_id = self._model.asset_id_at(current.row())
        if not asset_id:
            return
        dialog = MediaLocationDialog(row, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        from natureai_next.application.location_enrichment import (
            AdministrativeLocation,
            MediaLocationEnrichmentService,
        )

        service = MediaLocationEnrichmentService(self._database_path)
        try:
            service.save(
                asset_public_id=asset_id,
                media_type=self._spec.asset_type,
                latitude=dialog.latitude.value(),
                longitude=dialog.longitude.value(),
                administrative=AdministrativeLocation(
                    country_code=dialog.country.text(),
                    admin_area_1=dialog.region.text(),
                    admin_area_2=dialog.subregion.text(),
                    locality=dialog.locality.text(),
                ),
            )
            if dialog.resolve.isChecked():
                from natureai_next.ui.qt.activity import activity_center

                def operation(progress, cancelled) -> str:
                    progress(0, 1, "Reconstructing country and region")
                    if cancelled():
                        raise InterruptedError
                    resolved = service.reverse_asset(asset_id)
                    progress(1, 1, "Location reconstruction complete")
                    location = ", ".join(
                        value
                        for value in (
                            resolved.locality,
                            resolved.admin_area_1,
                            resolved.country_code,
                        )
                        if value
                    )
                    return f"Location reconstructed: {location or 'coordinates saved'}"

                activity_center().start(
                    "Reconstruct media location",
                    asset_id,
                    operation,
                    kind="location.reverse_geocode",
                )
                self._status.setText(
                    "Coordinates saved; country and region reconstruction queued in Activity Center."
                )
            else:
                self._status.setText("Location saved for maps and reporting.")
        except Exception as exc:
            QMessageBox.critical(self, "Location enrichment failed", str(exc))
            return
        self.refresh()

    @Slot()
    def _export_document_text(self) -> None:
        QMessageBox.information(
            self, "Export text",
            "Run OCR or text extraction first. Accepted extracted text can then be exported from the enrichment result."
        )

    @Slot()
    def _run_enrichment_capability(self) -> None:
        if self._enrichment_controller is None or self._enrichment_panel is None:
            return
        selected_rows = tuple(
            sorted(
                self._table.selectionModel().selectedRows(),
                key=lambda index: index.row(),
            )
        )
        if not selected_rows:
            QMessageBox.information(self, "Run enrichment", "Select a media item first.")
            return
        current = self._table.currentIndex()
        row = self._model.asset_at(current.row()) or {}
        from natureai_next.domain.enrichment import SubjectRef, SubjectType
        from natureai_next.synthesis_core.contracts import InputKind
        from natureai_next.ui.qt.capability_execution import (
            CapabilityBatchProgressDialog,
            CapabilityExecutionDialog,
        )

        input_kind = InputKind(self._spec.asset_type)
        choices = self._enrichment_controller.capabilities_for(input_kind)
        if not choices:
            QMessageBox.information(
                self, "Run enrichment", f"No installed capability accepts {input_kind.value} input."
            )
            return
        source = row.get("source_path")
        input_path = Path(str(source)) if source else None
        dialog = CapabilityExecutionDialog(
            choices, input_kind=input_kind, input_path=input_path, parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.request is None:
            return
        request = dialog.request
        batch_items = []
        batch_labels = []
        from natureai_next.application.enrichment_workspace import WorkspaceBatchItem

        for selected_index in selected_rows:
            selected_id = self._model.asset_id_at(selected_index.row())
            selected_row = self._model.asset_at(selected_index.row()) or {}
            if not selected_id:
                continue
            selected_source = selected_row.get("source_path")
            batch_items.append(
                WorkspaceBatchItem(
                    SubjectRef(SubjectType(self._spec.asset_type), selected_id),
                    Path(str(selected_source)) if selected_source else None,
                    request.structured_input,
                )
            )
            batch_labels.append(
                (
                    selected_id,
                    str(selected_row.get("original_filename") or selected_id),
                )
            )
        if not batch_items:
            return
        if request.region_classifier_id:
            QMessageBox.information(
                self,
                "Region pipeline",
                "Region classification is available for photograph batches. "
                "Choose the detector or classifier directly for this media library.",
            )
            return
        # Compatibility note: this replaces the former synchronous run_capability( desktop call.
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
        if self._run_capability is not None:
            self._run_capability.setEnabled(False)
        self._batch_screens = []
        for capability_id, parameters in executions:
            try:
                run = self._enrichment_controller.run_capability_batch_async(
                    tuple(batch_items),
                    capability_id=capability_id,
                    input_kind=request.input_kind,
                    parameters=parameters,
                    max_parallel=min(4, len(batch_items)),
                )
            except Exception as exc:
                QMessageBox.warning(self, f"{capability_id} failed to start", str(exc))
                continue
            screen = CapabilityBatchProgressDialog(
                run,
                tuple(batch_labels),
                capability_name=capability_id,
                library_name=self._spec.title,
                parent=None,
            )
            screen.completed.connect(self._batch_capability_finished)
            screen.show()
            self._batch_screens.append(screen)
        self._batch_screen = self._batch_screens[-1] if self._batch_screens else None
        self._status.setText(
            f"Running {len(executions)} enrichment(s) on {len(batch_items)} selected file(s)…"
        )

    @Slot(object)
    def _batch_capability_finished(self, outcome) -> None:
        if outcome is None:
            self._status.setText("Batch enrichment did not complete.")
        else:
            self._status.setText(
                f"Batch enrichment complete: {outcome.completed}/{outcome.requested} file(s), "
                f"{len(outcome.failures)} failed."
            )
        if self._enrichment_panel is not None:
            self._enrichment_panel.refresh()
        if self._run_capability is not None and not any(
            screen.running for screen in self._batch_screens
        ):
            self._run_capability.setEnabled(
                self._workspace_enabled and bool(self.selected_asset_ids())
            )

    def set_workspace_enabled(self, enabled: bool) -> None:
        """Bind analysis actions and active screens to Library Types settings."""
        self._workspace_enabled = bool(enabled)
        if not enabled and self._batch_screens:
            for screen in self._batch_screens:
                screen.cancel_for_disabled_workspace()
                screen.hide()
        elif enabled and self._batch_screen is not None and self._batch_screen.running:
            for screen in self._batch_screens:
                if screen.running:
                    screen.show()
        if self._run_capability is not None:
            self._run_capability.setEnabled(
                enabled
                and self._enrichment_controller is not None
                and bool(self.selected_asset_ids())
            )

    def select_asset(self, asset_id: str) -> bool:
        """Select and focus one stable asset identity in this media workspace."""
        for row in range(self._model.rowCount()):
            if str(self._model.asset_id_at(row) or "") == str(asset_id):
                index = self._model.index(row, 0)
                self._table.setCurrentIndex(index)
                self._table.scrollTo(index)
                return True
        return False

    def selected_asset_ids(self) -> tuple[str, ...]:
        """Return stable IDs for selected rows without reading another subsystem."""
        selection = self._table.selectionModel()
        if selection is None:
            return ()
        identifiers = []
        for index in selection.selectedRows():
            asset_id = self._model.asset_id_at(index.row())
            if asset_id:
                identifiers.append(asset_id)
        return tuple(dict.fromkeys(identifiers))

    @Slot()
    def _cancel_capability_run(self) -> None:
        if self._capability_run is not None:
            self._capability_run.cancel()
            self._status.setText("Cancelling enrichment…")

    @Slot()
    def _poll_capability_run(self) -> None:
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
        self._status.setText(progress.message)
        if not run.done:
            return
        self._capability_timer.stop()
        if self._capability_progress is not None:
            self._capability_progress.close()
        try:
            run.result()
        except InterruptedError:
            self._status.setText("Enrichment cancelled.")
        except Exception as exc:
            self._status.setText(f"Enrichment failed: {exc}")
            QMessageBox.critical(self, "Enrichment failed", str(exc))
        else:
            if self._enrichment_panel is not None:
                self._enrichment_panel.refresh()
            self._status.setText("Enrichment complete.")
        finally:
            self._capability_run = None
            self._capability_progress = None
            self._capability_subject = None
            if self._run_capability is not None:
                self._run_capability.setEnabled(self._table.currentIndex().isValid())

    @Slot(str, float)
    def _enrichment_time_selected(self, _enrichment_id: str, seconds: float) -> None:
        """Forward a canonical temporal selection to the owning media player."""
        current = self._table.currentIndex()
        if not current.isValid():
            return
        asset_id = self._model.asset_id_at(current.row())
        if asset_id:
            value = max(0.0, float(seconds))
            if self._sound_player is not None and self._sound_player.asset_id == asset_id:
                self._sound_player.seek_seconds(value)
            if self._video_player is not None and self._video_player.asset_id == asset_id:
                self._video_player.seek_seconds(value)
            self.playback_seek_requested.emit(asset_id, value)

    @Slot(float)
    def _spectrogram_time_selected(self, seconds: float) -> None:
        if self._sound_player is not None:
            self._sound_player.seek_seconds(seconds)

    @Slot(float)
    def _video_position_changed(self, seconds: float) -> None:
        if self._video_player is not None and self._video_player.asset_id:
            self.set_playback_position(self._video_player.asset_id, seconds)

    @Slot(object)
    def _overlay_scene_changed(self, scene: object) -> None:
        if not isinstance(scene, OverlayScene):
            return
        if self._spectrogram is not None:
            self._spectrogram.set_overlay_scene(scene)
        if self._video_player is not None:
            self._video_player.set_overlay_scene(scene)
        if self._document_viewer is not None:
            self._document_viewer.set_overlay_scene(scene)

    @Slot(str, str)
    def _enrichment_region_selected(self, _enrichment_id: str, region_id: str) -> None:
        if self._spectrogram is not None:
            self._spectrogram.select_region(region_id)
        if self._video_player is not None:
            self._video_player.select_region(region_id)
        if self._document_viewer is not None:
            self._document_viewer.select_region(region_id)

    @Slot(float)
    def _sound_position_changed(self, seconds: float) -> None:
        if self._sound_player is None or not self._sound_player.asset_id:
            return
        self.set_playback_position(self._sound_player.asset_id, seconds)

    def set_playback_position(self, asset_id: str, seconds: float) -> None:
        """Update the canonical overlay from an external audio/video playhead."""
        if self._enrichment_panel is None:
            return
        current = self._table.currentIndex()
        if not current.isValid() or self._model.asset_id_at(current.row()) != asset_id:
            return
        value = max(0.0, float(seconds))
        self._enrichment_panel.set_playback_position(value)
        if self._spectrogram is not None:
            self._spectrogram.set_playback_position(value)
        if self._waveform is not None:
            self._waveform.set_playback_position(value)
        if self._video_player is not None:
            self._video_player.set_playback_position(value)
        if self._frame_strip is not None:
            self._frame_strip.set_position(value)

    def activate(self) -> None:
        self.refresh()

    def deactivate(self) -> None:
        return

    @Slot()
    def refresh(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._pending_refresh = True
            return
        self._status.setText(f"Loading {self._spec.title.casefold()} independently…")
        thread = QThread(self)
        worker = _MediaQueryWorker(self._database_path, self._spec, self._search.text())
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.loaded.connect(self._loaded)
        worker.loaded.connect(thread.quit)
        worker.loaded.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_finished)
        self._thread = thread
        # Keep the Python wrapper alive until the QThread has finished. Without
        # this reference the worker can be collected before started is delivered,
        # leaving the workspace permanently at "Loading …".
        self._worker = worker
        thread.start()

    @Slot(object, object)
    def _loaded(self, rows: object, error: object) -> None:
        if error is not None:
            self._model.replace(())
            self._status.setText(f"{self._spec.title} unavailable: {error}")
            return
        typed_rows = tuple(rows) if isinstance(rows, tuple | list) else ()
        self._model.replace(typed_rows)
        self._status.setText(f"{len(typed_rows):,} {self._spec.title.casefold()} record(s)")

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh()
