"""Offline-map domain projections."""

from __future__ import annotations

from dataclasses import dataclass
import json


@dataclass(frozen=True, slots=True)
class OfflineMapPackage:
    public_id: str
    provider_key: str
    package_name: str
    package_version: str
    format: str
    package_path: str
    installed_at_us: int
    attribution: str = ""
    min_zoom: int | None = None
    max_zoom: int | None = None
    west: float | None = None
    south: float | None = None
    east: float | None = None
    north: float | None = None
    checksum_sha256: str | None = None
    enabled: bool = True
    status: str = "installed"
    verification_message: str = ""
    verified_size_bytes: int | None = None
    observed_checksum_sha256: str | None = None
    provider_metadata_json: str = "{}"
    tile_scheme: str = "tms"
    data_license: str = ""
    attribution_url: str = ""


def map_package_role(package: OfflineMapPackage) -> str:
    """Return the declared presentation role without trusting malformed metadata."""
    try:
        metadata = json.loads(getattr(package, "provider_metadata_json", "{}"))
    except (TypeError, json.JSONDecodeError):
        return "basemap"
    return str(metadata.get("map_role") or "basemap")


def is_nautical_overlay(package: OfflineMapPackage) -> bool:
    return map_package_role(package) == "nautical-overlay"


@dataclass(frozen=True, slots=True)
class OfflineRasterTile:
    zoom: int
    x: int
    y: int
    data: bytes
    media_type: str
    attribution: str
    attribution_url: str


@dataclass(frozen=True, slots=True)
class GpsTrackPoint:
    latitude: float
    longitude: float
    elevation_m: float | None = None
    recorded_at: str | None = None


@dataclass(frozen=True, slots=True)
class GpsTrack:
    name: str
    segments: tuple[tuple[GpsTrackPoint, ...], ...]

    @property
    def point_count(self) -> int:
        return sum(len(segment) for segment in self.segments)


@dataclass(frozen=True, slots=True)
class MapPackageCapability:
    """Renderer readiness for one installed map package."""

    package_public_id: str
    package_name: str
    package_format: str
    renderable: bool
    renderer_key: str | None
    status: str
    message: str
    max_zoom: int | None = None


@dataclass(frozen=True, slots=True)
class VectorRendererReadiness:
    """Platform readiness for the optional street-level vector renderer."""

    webengine_available: bool
    assets_available: bool
    archive_bridge_available: bool
    status: str
    message: str


@dataclass(frozen=True, slots=True)
class MapArchiveSlice:
    """One bounded byte range from an installed map archive."""

    package_public_id: str
    offset: int
    total_size: int
    data: bytes
    media_type: str = "application/vnd.pmtiles"
    checksum_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class MapArchiveRangeResponse:
    """Transport-neutral response to one browser byte-range request."""

    status_code: int
    content_range: str
    accept_ranges: str
    content_length: int
    media_type: str
    data: bytes
    checksum_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class RendererAssetReadiness:
    valid: bool
    status: str
    message: str


@dataclass(frozen=True, slots=True)
class StreetPackageProfile:
    schema: str
    layers: frozenset[str]
    label_fields: frozenset[str]
    max_zoom: int | None
    attribution: str
    data_license: str


def validate_street_package_profile(profile: StreetPackageProfile) -> tuple[bool, str]:
    required_layers = frozenset({"landuse", "water", "building", "transportation", "place"})
    if profile.schema != "aperture-streets-v1":
        return False, "Package does not declare the aperture-streets-v1 schema"
    missing = sorted(required_layers - profile.layers)
    if missing:
        return False, "Package is missing required street layers: " + ", ".join(missing)
    if not {"transportation.name", "place.name"}.issubset(profile.label_fields):
        return False, "Package does not declare the required road and place label fields"
    if profile.max_zoom is None or profile.max_zoom < 14:
        return False, "Package does not provide the required vector base zoom 14 coverage"
    if not profile.attribution.strip() or not profile.data_license.strip():
        return False, "Package attribution or data licence is missing"
    return True, "Package conforms to aperture-streets-v1"
