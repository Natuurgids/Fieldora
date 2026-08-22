"""Calendar widget that highlights scheduled dates and renders activity counts."""

from __future__ import annotations

from PySide6.QtCore import QDate, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QTextCharFormat
from PySide6.QtWidgets import QCalendarWidget


class ActivityCountCalendar(QCalendarWidget):
    """A standard accessible calendar with unobtrusive per-day count badges."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._counts: dict[str, int] = {}

    def set_activity_counts(self, counts: dict[str, int]) -> None:
        for iso_date in self._counts:
            day = QDate.fromString(iso_date, Qt.DateFormat.ISODate)
            if day.isValid():
                self.setDateTextFormat(day, QTextCharFormat())
        self._counts = {key: value for key, value in counts.items() if value > 0}
        for iso_date in self._counts:
            day = QDate.fromString(iso_date, Qt.DateFormat.ISODate)
            if not day.isValid():
                continue
            style = QTextCharFormat()
            style.setBackground(QColor("#234a3b"))
            style.setForeground(QColor("#f4fff8"))
            style.setFontWeight(600)
            self.setDateTextFormat(day, style)
        self.updateCells()

    def paintCell(self, painter: QPainter, rect: QRect, date: QDate) -> None:
        super().paintCell(painter, rect, date)
        count = self._counts.get(date.toString(Qt.DateFormat.ISODate), 0)
        if count <= 0:
            return
        badge_size = max(14, min(20, rect.height() // 3))
        badge = QRect(
            rect.right() - badge_size - 2,
            rect.top() + 2,
            badge_size,
            badge_size,
        )
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#d2a84b"))
        painter.drawEllipse(badge)
        painter.setPen(QColor("#17130a"))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, "99+" if count > 99 else str(count))
        painter.restore()
