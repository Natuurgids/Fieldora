"""Responsive Fieldora startup splash with real milestone progress."""

from __future__ import annotations

from pathlib import Path
from typing import Final

try:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QSplashScreen
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc

_SPLASH_SIZE: Final[tuple[int, int]] = (680, 360)


class FieldoraStartupSplash(QSplashScreen):
    """Small, paint-only splash that remains responsive during bootstrap."""

    def __init__(self, *, version: str, library_name: str = "") -> None:
        canvas = QPixmap(*_SPLASH_SIZE)
        canvas.fill(QColor("#11151a"))
        super().__init__(canvas, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self._version = version
        self._library_name = library_name
        self._stage = "Starting Fieldora…"
        self._detail = ""
        self._progress = 2
        self._logo = self._load_logo()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

    @staticmethod
    def _load_logo() -> QPixmap:
        icon_path = Path(__file__).resolve().parents[2] / "resources" / "fieldora.ico"
        if not icon_path.exists():
            return QPixmap()
        return QIcon(str(icon_path)).pixmap(112, 112)

    def set_stage(self, stage: str, progress: int, detail: str = "") -> None:
        self._stage = stage
        self._progress = max(0, min(100, int(progress)))
        self._detail = detail
        self.repaint()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#11151a"))

        if not self._logo.isNull():
            painter.drawPixmap(42, 39, self._logo)

        painter.setPen(QColor("#f4f7fa"))
        title_font = QFont()
        title_font.setPointSize(28)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRect(178, 53, 455, 54), Qt.AlignmentFlag.AlignLeft, "FIELDORA")

        subtitle_font = QFont()
        subtitle_font.setPointSize(10)
        painter.setFont(subtitle_font)
        painter.setPen(QColor("#aeb8c2"))
        painter.drawText(
            QRect(181, 106, 440, 30),
            Qt.AlignmentFlag.AlignLeft,
            "Offline biodiversity research & scientific projects",
        )

        painter.setPen(QColor("#e7edf3"))
        stage_font = QFont()
        stage_font.setPointSize(12)
        stage_font.setBold(True)
        painter.setFont(stage_font)
        painter.drawText(QRect(44, 191, 590, 28), Qt.AlignmentFlag.AlignLeft, self._stage)

        detail = self._detail or (f"Library: {self._library_name}" if self._library_name else "")
        painter.setFont(subtitle_font)
        painter.setPen(QColor("#aeb8c2"))
        painter.drawText(QRect(44, 224, 590, 24), Qt.AlignmentFlag.AlignLeft, detail)

        bar = QRect(44, 267, 592, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#2c343d"))
        painter.drawRoundedRect(bar, 6, 6)
        fill_width = max(12, round(bar.width() * self._progress / 100))
        painter.setBrush(QColor("#d8e3ec"))
        painter.drawRoundedRect(QRect(bar.x(), bar.y(), fill_width, bar.height()), 6, 6)

        painter.setPen(QColor("#84909b"))
        painter.drawText(QRect(44, 296, 480, 24), Qt.AlignmentFlag.AlignLeft, self._version)
        painter.drawText(QRect(550, 296, 86, 24), Qt.AlignmentFlag.AlignRight, f"{self._progress}%")
        painter.end()


def create_startup_splash(
    *, version: str, library_name: str
) -> tuple[QApplication, FieldoraStartupSplash]:
    """Create the shared QApplication and display the splash immediately."""
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Fieldora")
    app.setOrganizationName("natuurgids.org")
    splash = FieldoraStartupSplash(version=version, library_name=library_name)
    splash.show()
    splash.set_stage("Opening Fieldora Library…", 12)
    return app, splash
