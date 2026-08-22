"""Map-ready spatial and longitudinal domain projections."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeoBounds:
    min_latitude: float
    min_longitude: float
    max_latitude: float
    max_longitude: float

    def __post_init__(self) -> None:
        if not (-90 <= self.min_latitude <= self.max_latitude <= 90):
            raise ValueError("invalid latitude bounds")
        if not (-180 <= self.min_longitude <= self.max_longitude <= 180):
            raise ValueError("invalid longitude bounds")


@dataclass(frozen=True, slots=True)
class SpatialObservation:
    observation_public_id: str
    observed_at_us: int
    latitude: float
    longitude: float
    scientific_name: str | None
    site_public_id: str | None
    project_public_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SpatialAsset:
    asset_public_id: str
    latitude: float
    longitude: float
    captured_at_us: int | None
    location_role: str = "capture"
    media_type: str = "image"


@dataclass(frozen=True, slots=True)
class SpatialAssetCluster:
    latitude: float
    longitude: float
    total_count: int
    image_count: int
    video_count: int
    audio_count: int
    capture_count: int
    subject_count: int
    user_defined_count: int
    level: str
    label: str


@dataclass(frozen=True, slots=True)
class MonitoringSiteSummary:
    public_id: str
    name: str
    latitude: float | None
    longitude: float | None
    status: str
