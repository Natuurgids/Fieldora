"""Phase E contribution and conflict review panel."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)


class SynchronizationReviewPanel(QWidget):
    acknowledgment_requested = Signal()
    conflict_resolution_requested = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._summary = QLabel("No pending contributions")
        self._acknowledge = QPushButton("Review and acknowledge terms…")
        self._acknowledge.clicked.connect(self.acknowledgment_requested.emit)
        self._conflicts = QTableWidget(0, 4)
        self._conflicts.setHorizontalHeaderLabels(
            ["Record", "Local revision", "Remote revision", "Resolution"]
        )
        buttons = QHBoxLayout()
        for label, resolution in (
            ("Keep local", "keep_local"),
            ("Accept remote", "accept_remote"),
            ("Manual merge", "manual"),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, value=resolution: self._resolve_selected(value)
            )
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(self._summary)
        layout.addWidget(self._acknowledge)
        layout.addWidget(self._conflicts)
        layout.addLayout(buttons)

    def show_preview(self, preview) -> None:
        self._summary.setText(
            f"{preview.change_count} changes: {preview.creates_or_updates} updates, "
            f"{preview.deletions} deletions"
        )

    def show_conflicts(self, conflicts) -> None:
        self._conflicts.setRowCount(len(conflicts))
        for row, conflict in enumerate(conflicts):
            values = (
                conflict.aggregate_id, str(conflict.local_revision),
                str(conflict.remote_revision), "Unresolved",
            )
            for column, value in enumerate(values):
                self._conflicts.setItem(row, column, QTableWidgetItem(value))
            self._conflicts.item(row, 0).setData(256, conflict.conflict_id)

    def _resolve_selected(self, resolution: str) -> None:
        row = self._conflicts.currentRow()
        if row >= 0 and self._conflicts.item(row, 0) is not None:
            self.conflict_resolution_requested.emit(
                str(self._conflicts.item(row, 0).data(256)), resolution
            )
