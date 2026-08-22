"""Application-facing spatial query contracts."""

from __future__ import annotations

from typing import Protocol

from natureai_next.domain.spatial_intelligence import GeoBounds
from natureai_next.domain.temporal_movement import MovementTrack, TemporalObservationPoint


class TemporalSpatialQuery(Protocol):
    def observations_in_time_window(
        self,
        bounds: GeoBounds,
        *,
        start_us: int,
        end_us: int,
        cumulative: bool = False,
        limit: int = 5000,
    ) -> tuple[TemporalObservationPoint, ...]: ...

    def movement_track(
        self,
        series_public_id: str,
        *,
        start_us: int | None = None,
        end_us: int | None = None,
    ) -> MovementTrack: ...
