"""Playback-ready temporal map application service."""

from __future__ import annotations

from dataclasses import dataclass

from natureai_next.domain.spatial_intelligence import GeoBounds
from natureai_next.domain.temporal_movement import (
    MovementEvidenceMode,
    MovementTrack,
    TemporalDisplayMode,
    TemporalObservationPoint,
    TemporalStep,
    TimeWindow,
    step_window,
)
from natureai_next.ports.spatial import TemporalSpatialQuery


@dataclass(frozen=True, slots=True)
class TemporalMapFrame:
    bounds: GeoBounds
    window: TimeWindow
    display_mode: TemporalDisplayMode
    evidence_mode: MovementEvidenceMode
    observations: tuple[TemporalObservationPoint, ...]
    track: MovementTrack | None = None


class TemporalMapService:
    def __init__(self, spatial: TemporalSpatialQuery) -> None:
        self._spatial = spatial

    def frame(
        self,
        *,
        bounds: GeoBounds,
        window: TimeWindow,
        display_mode: TemporalDisplayMode = TemporalDisplayMode.SNAPSHOT,
        series_public_id: str | None = None,
    ) -> TemporalMapFrame:
        cumulative = display_mode is TemporalDisplayMode.CUMULATIVE
        observations = self._spatial.observations_in_time_window(
            bounds, start_us=window.start_us, end_us=window.end_us, cumulative=cumulative
        )
        track = None
        evidence_mode = MovementEvidenceMode.OBSERVED_LOCATIONS
        if display_mode is TemporalDisplayMode.TRAIL:
            if not series_public_id:
                raise ValueError("trail mode requires a series public ID")
            track = self._spatial.movement_track(
                series_public_id, start_us=window.start_us, end_us=window.end_us
            )
            evidence_mode = track.evidence_mode
        elif observations:
            policies = {point.connection_policy for point in observations}
            if policies == {MovementEvidenceMode.CONFIRMED_MOVEMENT.value}:
                evidence_mode = MovementEvidenceMode.CONFIRMED_MOVEMENT
            elif MovementEvidenceMode.INFERRED_DISTRIBUTION.value in policies:
                evidence_mode = MovementEvidenceMode.INFERRED_DISTRIBUTION
        return TemporalMapFrame(bounds, window, display_mode, evidence_mode, observations, track)


@dataclass(slots=True)
class TemporalPlaybackState:
    window: TimeWindow
    step: TemporalStep = TemporalStep.MONTH
    display_mode: TemporalDisplayMode = TemporalDisplayMode.SNAPSHOT
    series_public_id: str | None = None
    loop: bool = False
    playing: bool = False

    def advance(self, *, direction: int = 1) -> TimeWindow:
        self.window = step_window(self.window, self.step, direction=direction)
        return self.window
