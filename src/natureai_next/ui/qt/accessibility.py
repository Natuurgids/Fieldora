"""Accessibility helpers for the Aperture Qt desktop shell."""

from __future__ import annotations

from dataclasses import dataclass

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (
        QAbstractButton,
        QDialog,
        QLabel,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required") from exc


@dataclass(frozen=True, slots=True)
class ShortcutEntry:
    action: str
    shortcut: str
    context: str


CORE_SHORTCUTS = (
    ShortcutEntry("Import folder", "Ctrl+I", "Application"),
    ShortcutEntry("Open export", "Ctrl+E", "Application"),
    ShortcutEntry("Back up library", "Ctrl+Shift+B", "Application"),
    ShortcutEntry("Restore library", "Ctrl+Shift+R", "Application"),
    ShortcutEntry("Open context help", "F1", "Application"),
    ShortcutEntry("Open keyboard shortcuts", "Ctrl+/", "Application"),
    ShortcutEntry("Shutdown", "Ctrl+Q", "Application"),
    ShortcutEntry("Next suggestion", "J", "AI Review"),
    ShortcutEntry("Previous suggestion", "K", "AI Review"),
    ShortcutEntry("Accept suggestion", "A", "AI Review"),
    ShortcutEntry("Accept and continue", "Shift+Enter", "AI Review"),
    ShortcutEntry("Reject suggestion", "R", "AI Review"),
    ShortcutEntry("Defer suggestion", "D", "AI Review"),
    ShortcutEntry("Open observation history", "O", "AI Review"),
    ShortcutEntry("Reverse acceptance", "Ctrl+Z", "AI Review"),
    ShortcutEntry("Previous image", "Left / PgUp", "Viewer"),
    ShortcutEntry("Next image", "Right / PgDown", "Viewer"),
    ShortcutEntry("First image", "Home", "Viewer"),
    ShortcutEntry("Last image", "End", "Viewer"),
    ShortcutEntry("Fit image", "F", "Viewer"),
    ShortcutEntry("Actual size", "1", "Viewer"),
    ShortcutEntry("Zoom in", "+", "Viewer"),
    ShortcutEntry("Zoom out", "-", "Viewer"),
    ShortcutEntry("Save metadata", "Ctrl+S", "Library inspector"),
    ShortcutEntry("Discard metadata edits", "Esc", "Library inspector"),
)


def accessible_action_name(action: QAction) -> str:
    """Return menu text without mnemonic markers or ellipses."""
    return action.text().replace("&", "").replace("…", "").strip()


def apply_accessibility_defaults(root: QWidget) -> int:
    """Apply conservative accessible names and focus policy to child controls.

    Explicit names provided by a workspace always win. The helper only fills
    missing metadata, making new controls safer by default without changing
    workflow or visual design.
    """
    changed = 0
    for button in root.findChildren(QAbstractButton):
        if not button.accessibleName().strip():
            name = button.text().replace("&", "").replace("…", "").strip()
            if name:
                button.setAccessibleName(name)
                changed += 1
        if button.focusPolicy() == Qt.FocusPolicy.NoFocus:
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            changed += 1
    return changed


class KeyboardShortcutsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aperture Keyboard Shortcuts")
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        heading = QLabel(
            "<h2>Keyboard shortcuts</h2><p>These shortcuts are available throughout Aperture.</p>"
        )
        heading.setWordWrap(True)
        layout.addWidget(heading)
        table = QTableWidget(len(CORE_SHORTCUTS), 3, self)
        table.setHorizontalHeaderLabels(["Action", "Shortcut", "Context"])
        table.setAccessibleName("Aperture keyboard shortcuts")
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        for row, entry in enumerate(CORE_SHORTCUTS):
            table.setItem(row, 0, QTableWidgetItem(entry.action))
            table.setItem(row, 1, QTableWidgetItem(entry.shortcut))
            table.setItem(row, 2, QTableWidgetItem(entry.context))
        table.resizeColumnsToContents()
        layout.addWidget(table)
