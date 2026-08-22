"""Producer-neutral interaction models for canonical enrichment visualizations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NormalizedRegion:
    """A selectable region in normalized media coordinates."""

    region_id: str
    kind: str
    x: float
    y: float
    width: float
    height: float
    points: tuple[tuple[float, float], ...] = ()
    start_seconds: float | None = None
    end_seconds: float | None = None
    low_hz: float | None = None
    high_hz: float | None = None

    def contains(self, x: float, y: float) -> bool:
        px = _unit(x)
        py = _unit(y)
        if self.points:
            return _point_in_polygon(px, py, self.points)
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height


@dataclass(frozen=True, slots=True)
class OverlayScene:
    """Renderer-independent selectable scene for one canonical enrichment."""

    kind: str
    regions: tuple[NormalizedRegion, ...]
    duration_seconds: float | None = None
    maximum_hz: float | None = None

    def hit_test(self, x: float, y: float) -> NormalizedRegion | None:
        for region in reversed(self.regions):
            if region.contains(x, y):
                return region
        return None

    def region_at_time(self, seconds: float) -> NormalizedRegion | None:
        value = max(0.0, float(seconds))
        for region in self.regions:
            if region.start_seconds is None:
                continue
            end = region.end_seconds if region.end_seconds is not None else region.start_seconds
            if region.start_seconds <= value <= end:
                return region
        return None


def build_overlay_scene(
    enrichment_id: str,
    visualization: Mapping[str, Any] | None,
    *,
    duration_seconds: float | None = None,
    maximum_hz: float | None = None,
) -> OverlayScene:
    """Translate canonical visualization data into normalized interactive regions."""

    payload = dict(visualization or {})
    kind = str(payload.get("kind") or "summary")
    regions: list[NormalizedRegion] = []

    for index, box_value in enumerate(payload.get("boxes") or ()):
        box = dict(box_value)
        regions.append(
            NormalizedRegion(
                region_id=f"{enrichment_id}:box:{index}",
                kind="box",
                x=_unit(box.get("x")),
                y=_unit(box.get("y")),
                width=_extent(box.get("width")),
                height=_extent(box.get("height")),
            )
        )

    for index, polygon_value in enumerate(payload.get("polygons") or ()):
        points = tuple(_point(point) for point in polygon_value)
        if not points:
            continue
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        regions.append(
            NormalizedRegion(
                region_id=f"{enrichment_id}:polygon:{index}",
                kind="polygon",
                x=min(xs),
                y=min(ys),
                width=max(xs) - min(xs),
                height=max(ys) - min(ys),
                points=points,
            )
        )

    if kind == "document-region":
        box = dict(payload.get("box") or {})
        regions.append(
            NormalizedRegion(
                region_id=f"{enrichment_id}:document:0",
                kind="document-region",
                x=_unit(box.get("x")),
                y=_unit(box.get("y")),
                width=_extent(box.get("width")),
                height=_extent(box.get("height")),
            )
        )

    if kind in {"timeline", "time-frequency", "transcript"}:
        start = _number(payload.get("start_seconds"))
        end = max(start, _number(payload.get("end_seconds"), start))
        duration = max(end, _number(duration_seconds), 1.0)
        low_hz = _optional_number(payload.get("low_hz"))
        high_hz = _optional_number(payload.get("high_hz"))
        max_hz = max(_number(maximum_hz), high_hz or 0.0, 1.0)
        if kind == "time-frequency":
            low = max(0.0, low_hz or 0.0)
            high = max(low, high_hz if high_hz is not None else max_hz)
            y = _unit(1.0 - (high / max_hz))
            height = _extent((high - low) / max_hz)
        else:
            y = 0.0
            height = 1.0
        regions.append(
            NormalizedRegion(
                region_id=f"{enrichment_id}:time:0",
                kind=kind,
                x=_unit(start / duration),
                y=y,
                width=_extent((end - start) / duration),
                height=height,
                start_seconds=start,
                end_seconds=end,
                low_hz=low_hz,
                high_hz=high_hz,
            )
        )
        duration_seconds = duration
        maximum_hz = max_hz if kind == "time-frequency" else maximum_hz

    return OverlayScene(kind, tuple(regions), duration_seconds, maximum_hz)


def _point(value: object) -> tuple[float, float]:
    if isinstance(value, Mapping):
        return (_unit(value.get("x")), _unit(value.get("y")))
    if isinstance(value, Sequence) and not isinstance(value, str | bytes) and len(value) >= 2:
        return (_unit(value[0]), _unit(value[1]))
    return (0.0, 0.0)


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_number(value: object) -> float | None:
    if value is None or value == "":
        return None
    return _number(value)


def _unit(value: object) -> float:
    return min(1.0, max(0.0, _number(value)))


def _extent(value: object) -> float:
    return min(1.0, max(0.001, _number(value)))


def _point_in_polygon(x: float, y: float, points: tuple[tuple[float, float], ...]) -> bool:
    inside = False
    previous = points[-1]
    for current in points:
        x1, y1 = previous
        x2, y2 = current
        crosses = (y1 > y) != (y2 > y)
        if crosses:
            denominator = y2 - y1
            boundary = (x2 - x1) * (y - y1) / denominator + x1
            if x < boundary:
                inside = not inside
        previous = current
    return inside
