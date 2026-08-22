"""Temporal playback and scientifically qualified movement projections."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TemporalDisplayMode(str, Enum):
    SNAPSHOT = "snapshot"
    CUMULATIVE = "cumulative"
    TRAIL = "trail"


class TemporalStep(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    SEASON = "season"
    YEAR = "year"


class MovementEvidenceMode(str, Enum):
    OBSERVED_LOCATIONS = "observed_locations"
    INFERRED_DISTRIBUTION = "inferred_distribution"
    CONFIRMED_MOVEMENT = "confirmed_movement"


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start_us: int
    end_us: int

    def __post_init__(self) -> None:
        if self.end_us < self.start_us:
            raise ValueError("time window end precedes start")


@dataclass(frozen=True, slots=True)
class TemporalObservationPoint:
    observation_public_id: str
    observed_at_us: int
    latitude: float
    longitude: float
    scientific_name: str | None
    series_public_id: str | None
    identity_confidence: str
    connection_policy: str


@dataclass(frozen=True, slots=True)
class MovementTrackPoint:
    observation_public_id: str
    observed_at_us: int
    latitude: float
    longitude: float
    sequence_number: int | None
    identity_confidence: str
    verified: bool


@dataclass(frozen=True, slots=True)
class MovementTrack:
    series_public_id: str
    title: str
    subject_type: str
    subject_identifier: str | None
    identity_confidence: str
    tracking_method: str
    evidence_mode: MovementEvidenceMode
    points: tuple[MovementTrackPoint, ...]


def step_window(window: TimeWindow, step: TemporalStep, *, direction: int = 1) -> TimeWindow:
    """Advance a playback window using fixed UTC durations suitable for deterministic replay."""
    durations = {
        TemporalStep.DAY: 86_400_000_000,
        TemporalStep.WEEK: 7 * 86_400_000_000,
        TemporalStep.MONTH: 30 * 86_400_000_000,
        TemporalStep.SEASON: 91 * 86_400_000_000,
        TemporalStep.YEAR: 365 * 86_400_000_000,
    }
    delta = durations[step] * (1 if direction >= 0 else -1)
    return TimeWindow(window.start_us + delta, window.end_us + delta)
