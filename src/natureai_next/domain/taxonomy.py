"""Taxonomy and observation domain contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class TaxonStatus(StrEnum):
    ACCEPTED = "accepted"
    SYNONYM = "synonym"
    UNRESOLVED = "unresolved"


class ObservationType(StrEnum):
    ORGANISM = "organism"
    HABITAT = "habitat"
    LANDSCAPE = "landscape"
    UNKNOWN = "unknown"


class ConfirmationState(StrEnum):
    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class LicenseMetadata:
    name: str
    url: str | None
    attribution: str
    redistribution_allowed: bool

    def validate(self) -> None:
        if not self.name.strip() or not self.attribution.strip():
            raise ValueError("license name and attribution are required")


@dataclass(frozen=True, slots=True)
class TaxonRecord:
    source_taxon_id: str
    scientific_name: str
    rank: str
    status: TaxonStatus
    parent_source_taxon_id: str | None = None
    accepted_source_taxon_id: str | None = None
    authorship: str | None = None
    kingdom: str | None = None
    major_group: str | None = None
    extinct: bool = False

    def validate(self) -> None:
        if (
            not self.source_taxon_id.strip()
            or not self.scientific_name.strip()
            or not self.rank.strip()
        ):
            raise ValueError("taxon identity, scientific name, and rank are required")
        if self.status is TaxonStatus.SYNONYM and not self.accepted_source_taxon_id:
            raise ValueError("synonym requires accepted taxon")
        if self.parent_source_taxon_id == self.source_taxon_id:
            raise ValueError("taxon cannot parent itself")


@dataclass(frozen=True, slots=True)
class TaxonNameRecord:
    source_taxon_id: str
    name: str
    name_type: str
    source: str
    language_tag: str | None = None
    region_code: str | None = None
    preferred: bool = False


@dataclass(frozen=True, slots=True)
class TaxonRegionRecord:
    source_taxon_id: str
    region_code: str
    occurrence_status: str | None
    source: str


@dataclass(frozen=True, slots=True)
class TaxonomyPackageData:
    package_id: str
    source_name: str
    source_version: str
    minimum_app_version: str
    license: LicenseMetadata
    taxa: tuple[TaxonRecord, ...]
    names: tuple[TaxonNameRecord, ...]
    regions: tuple[TaxonRegionRecord, ...]
    checksum: str
    attribution_text: str


@dataclass(frozen=True, slots=True)
class TaxonSummary:
    public_id: str
    source_taxon_id: str
    scientific_name: str
    authorship: str | None
    rank: str
    status: str
    parent_public_id: str | None
    accepted_public_id: str | None
    preferred_name: str | None
    occurrence_status: str | None


@dataclass(frozen=True, slots=True)
class TaxonPage:
    items: tuple[TaxonSummary, ...]
    next_after_name: str | None


@dataclass(frozen=True, slots=True)
class TaxonKnowledgeProfile:
    public_id: str
    scientific_name: str
    authorship: str | None
    rank: str
    status: str
    preferred_names: tuple[str, ...]
    facts: tuple[dict[str, object], ...]
    distributions: tuple[dict[str, object], ...]
    links: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class ObservationDraft:
    observation_type: ObservationType
    confirmation_state: ConfirmationState = ConfirmationState.UNCONFIRMED
    taxon_public_id: str | None = None
    user_taxon_public_id: str | None = None
    life_stage: str | None = None
    sex: str | None = None
    count: int | None = None
    behavior: str | None = None
    notes: str | None = None
    roi_public_id: str | None = None

    def validate(self) -> None:
        if self.taxon_public_id and self.user_taxon_public_id:
            raise ValueError("observation cannot reference both taxon namespaces")
        if self.count is not None and self.count < 0:
            raise ValueError("count cannot be negative")


@dataclass(frozen=True, slots=True)
class ObservationView:
    public_id: str
    asset_public_id: str
    revision: int
    observation_type: str
    confirmation_state: str
    taxon_public_id: str | None
    user_taxon_public_id: str | None
    display_name: str | None
    life_stage: str | None
    sex: str | None
    count: int | None
    behavior: str | None
    notes: str | None
    roi_public_id: str | None


@dataclass(frozen=True, slots=True)
class RegionOfInterestDraft:
    shape_type: str
    coordinates: dict[str, Any]
    label: str | None = None

    def validate(self) -> None:
        if self.shape_type not in {"rectangle", "polygon"}:
            raise ValueError("unsupported ROI shape")
        values = self.coordinates.get("points")
        if not isinstance(values, list) or not values:
            raise ValueError("ROI points are required")
        for point in values:
            if (
                not isinstance(point, list)
                or len(point) != 2
                or any(not isinstance(v, int | float) or v < 0 or v > 1 for v in point)
            ):
                raise ValueError("ROI coordinates must be normalized pairs")
        if self.shape_type == "rectangle" and len(values) != 2:
            raise ValueError("rectangle requires two points")
        if self.shape_type == "polygon" and len(values) < 3:
            raise ValueError("polygon requires at least three points")
