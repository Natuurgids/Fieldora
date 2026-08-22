"""Reusable editable date/date-time field with calendar picker.

The text remains directly editable while the picker provides a validated system-date
starting point and an explicit action to copy the selected value into the field.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


DATETIME_FORMAT = "yyyy-MM-dd HH:mm"
DATE_FORMAT = "yyyy-MM-dd"


def system_datetime_text(*, include_time: bool = True) -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M" if include_time else "%Y-%m-%d")


class DateTimeTextField(QWidget):
    """Editable text field plus a date/time picker button."""

    def __init__(
        self,
        value: str | None = None,
        *,
        include_time: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.include_time = include_time
        self.line_edit = QLineEdit(value or system_datetime_text(include_time=include_time))
        self.line_edit.setPlaceholderText("YYYY-MM-DD HH:MM" if include_time else "YYYY-MM-DD")
        self.picker_button = QPushButton("Calendar…")
        self.picker_button.setToolTip("Choose a date and time and copy it into the field")
        self.picker_button.clicked.connect(self.open_picker)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.line_edit, 1)
        layout.addWidget(self.picker_button)

    def text(self) -> str:
        return self.line_edit.text().strip()

    def setText(self, value: str) -> None:
        self.line_edit.setText(value)

    def open_picker(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Select date and time" if self.include_time else "Select date")
        editor = QDateTimeEdit(dialog)
        editor.setCalendarPopup(True)
        editor.setDisplayFormat(DATETIME_FORMAT if self.include_time else DATE_FORMAT)
        editor.setDateTime(self._parsed_or_current())
        if not self.include_time:
            editor.setTimeSpec(editor.timeSpec())

        use_button = QPushButton("Use selected date and time" if self.include_time else "Use selected date")
        cancel_button = QPushButton("Cancel")
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(use_button)
        row.addWidget(cancel_button)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Select the required date and time:" if self.include_time else "Select the required date:"))
        layout.addWidget(editor)
        layout.addLayout(row)
        cancel_button.clicked.connect(dialog.reject)

        def apply_value() -> None:
            self.line_edit.setText(editor.dateTime().toString(DATETIME_FORMAT if self.include_time else DATE_FORMAT))
            dialog.accept()

        use_button.clicked.connect(apply_value)
        dialog.exec()

    def _parsed_or_current(self) -> QDateTime:
        value = self.text()
        formats = (
            ("yyyy-MM-dd HH:mm", "yyyy-MM-ddTHH:mm", "yyyy-MM-dd HH:mm:ss", "yyyy-MM-ddTHH:mm:ss")
            if self.include_time
            else ("yyyy-MM-dd",)
        )
        for fmt in formats:
            parsed = QDateTime.fromString(value, fmt)
            if parsed.isValid():
                return parsed
        return QDateTime.currentDateTime()


def get_datetime_text(
    parent: QWidget | None,
    title: str,
    label: str,
    *,
    value: str | None = None,
    include_time: bool = True,
) -> tuple[str, bool]:
    """Display a small dialog with direct text entry and a calendar picker."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    field = DateTimeTextField(value, include_time=include_time, parent=dialog)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(label))
    layout.addWidget(field)
    layout.addWidget(buttons)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return field.text(), accepted
