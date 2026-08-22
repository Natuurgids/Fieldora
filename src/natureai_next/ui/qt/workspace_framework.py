"""Reusable media-workspace composition primitives introduced for Build 33.5.

The framework deliberately owns layout behaviour only. Domain queries, playback,
enrichment, review and persistence remain in their existing controllers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

try:
    from PySide6.QtCore import QSettings, Qt, Signal
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


@dataclass(frozen=True, slots=True)
class WorkspaceAction:
    key: str
    label: str
    callback: Callable[[], None]
    requires_selection: bool = False


@dataclass(frozen=True, slots=True)
class MediaWorkspaceDescriptor:
    media_type: str
    title: str
    inspector_sections: tuple[str, ...]
    actions: tuple[str, ...]


class CollapsibleSection(QWidget):
    """Standard zero-height collapsible container used across Aperture workspaces."""

    collapsed_changed = Signal(bool)

    def __init__(
        self,
        title: str,
        content: QWidget,
        parent: QWidget | None = None,
        *,
        settings_key: str | None = None,
        collapsed: bool = False,
    ) -> None:
        super().__init__(parent)
        self._content = content
        self._settings_key = settings_key
        if settings_key:
            collapsed = bool(QSettings().value(settings_key, collapsed, type=bool))
        self._toggle = QToolButton(self)
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(not collapsed)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.clicked.connect(lambda checked: self.set_collapsed(not checked))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._toggle)
        layout.addWidget(content)
        self.set_collapsed(collapsed, persist=False)

    @property
    def is_collapsed(self) -> bool:
        return not self._content.isVisible()

    def set_collapsed(self, collapsed: bool, *, persist: bool = True) -> None:
        collapsed = bool(collapsed)
        self._toggle.setChecked(not collapsed)
        self._toggle.setArrowType(Qt.ArrowType.RightArrow if collapsed else Qt.ArrowType.DownArrow)
        self._content.setVisible(not collapsed)
        self._content.setMaximumHeight(0 if collapsed else 16777215)
        self._content.setMinimumHeight(0)
        self.layout().setSpacing(0)
        if persist and self._settings_key:
            QSettings().setValue(self._settings_key, collapsed)
        self.updateGeometry()
        if self.parentWidget() is not None:
            self.parentWidget().updateGeometry()
        self.collapsed_changed.emit(collapsed)


class AdaptiveActionBar(QFrame):
    """Media-aware bottom command surface with stable status placement."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mediaActionBar")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 5, 10, 5)
        self._status = QLabel()
        self._layout.addWidget(self._status, 1)
        self._buttons: dict[str, QPushButton] = {}

    @property
    def status_label(self) -> QLabel:
        return self._status

    def set_actions(self, actions: tuple[WorkspaceAction, ...]) -> None:
        for button in self._buttons.values():
            self._layout.removeWidget(button)
            button.deleteLater()
        self._buttons.clear()
        for action in actions:
            button = QPushButton(action.label, self)
            button.clicked.connect(action.callback)
            button.setProperty("requiresSelection", action.requires_selection)
            button.setEnabled(not action.requires_selection)
            self._layout.addWidget(button)
            self._buttons[action.key] = button

    def set_selection_available(self, available: bool) -> None:
        for button in self._buttons.values():
            if bool(button.property("requiresSelection")):
                button.setEnabled(available)

    def button(self, key: str) -> QPushButton | None:
        return self._buttons.get(key)


class MediaWorkspaceHost(QWidget):
    """Stable shell: command/filter area, replaceable center, docked inspector and action bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 10)
        self._layout.setSpacing(7)

    def compose(
        self,
        *,
        command_bar: QWidget,
        filters: QWidget,
        workspace: QWidget,
        action_bar: QWidget,
    ) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
        self._layout.addWidget(command_bar)
        self._layout.addWidget(filters)
        self._layout.addWidget(workspace, 1)
        self._layout.addWidget(action_bar)
