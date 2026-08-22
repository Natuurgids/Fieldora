"""Viewer navigation, zoom, and pan state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ZoomMode(StrEnum):
    FIT = "fit"
    ACTUAL = "actual"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class ViewerState:
    ordered_ids: tuple[str, ...] = ()
    index: int = -1
    zoom_mode: ZoomMode = ZoomMode.FIT
    zoom_factor: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0

    @property
    def current_id(self) -> str | None:
        if self.index < 0 or self.index >= len(self.ordered_ids):
            return None
        return self.ordered_ids[self.index]

    @property
    def can_previous(self) -> bool:
        return self.index > 0

    @property
    def can_next(self) -> bool:
        return 0 <= self.index < len(self.ordered_ids) - 1


class ViewerPresenter:
    """Framework-independent viewer state with bounded navigation and zoom."""

    MIN_ZOOM = 0.05
    MAX_ZOOM = 32.0

    def __init__(self) -> None:
        self.state = ViewerState()

    def open(self, ordered_ids: tuple[str, ...], public_id: str) -> None:
        if not ordered_ids:
            raise ValueError("viewer requires at least one asset")
        if public_id not in ordered_ids:
            raise ValueError("selected asset is not in viewer ordering")
        self.state = ViewerState(ordered_ids=ordered_ids, index=ordered_ids.index(public_id))

    def next(self) -> bool:
        return self._move_to(self.state.index + 1)

    def previous(self) -> bool:
        return self._move_to(self.state.index - 1)

    def first(self) -> bool:
        return self._move_to(0)

    def last(self) -> bool:
        return self._move_to(len(self.state.ordered_ids) - 1)

    def fit(self) -> None:
        self._set_zoom(ZoomMode.FIT, 1.0)

    def actual(self) -> None:
        self._set_zoom(ZoomMode.ACTUAL, 1.0)

    def zoom(self, factor: float) -> None:
        if not self.MIN_ZOOM <= factor <= self.MAX_ZOOM:
            raise ValueError("zoom outside supported range")
        self._set_zoom(ZoomMode.CUSTOM, factor)

    def zoom_by(self, multiplier: float) -> None:
        if multiplier <= 0:
            raise ValueError("zoom multiplier must be positive")
        current = self.state.zoom_factor if self.state.zoom_mode is ZoomMode.CUSTOM else 1.0
        self.zoom(max(self.MIN_ZOOM, min(self.MAX_ZOOM, current * multiplier)))

    def pan(self, x: float, y: float) -> None:
        self.state = ViewerState(
            ordered_ids=self.state.ordered_ids,
            index=self.state.index,
            zoom_mode=self.state.zoom_mode,
            zoom_factor=self.state.zoom_factor,
            pan_x=x,
            pan_y=y,
        )

    def _move_to(self, index: int) -> bool:
        if index < 0 or index >= len(self.state.ordered_ids) or index == self.state.index:
            return False
        self.state = ViewerState(ordered_ids=self.state.ordered_ids, index=index)
        return True

    def _set_zoom(self, mode: ZoomMode, factor: float) -> None:
        self.state = ViewerState(
            ordered_ids=self.state.ordered_ids,
            index=self.state.index,
            zoom_mode=mode,
            zoom_factor=factor,
            pan_x=self.state.pan_x,
            pan_y=self.state.pan_y,
        )
