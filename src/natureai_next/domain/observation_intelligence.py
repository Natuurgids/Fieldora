"""Personal observation-history projections."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PersonalObservationContext:
    taxon_public_id: str
    confirmed_observations: int
    evidence_photos: int
    first_observed_at_us: int | None
    last_observed_at_us: int | None
    country_codes: tuple[str, ...]

    @property
    def is_first_observation(self) -> bool:
        return self.confirmed_observations == 0


@dataclass(frozen=True, slots=True)
class ObservationInspectorRecord:
    public_id: str
    taxon_public_id: str | None
    scientific_name: str | None
    confirmation_state: str
    created_at_us: int
    modified_at_us: int
    revision: int
    asset_public_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SpeciesObservationSummary:
    taxon_public_id: str
    scientific_name: str
    rank: str | None
    observation_count: int
    evidence_photo_count: int
    first_observed_at_us: int | None
    last_observed_at_us: int | None
    country_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ObservationEvidencePhoto:
    asset_public_id: str
    primary_path: str | None
    thumbnail_path: str | None
    captured_at_us: int | None
    capture_local_text: str | None
    country_code: str | None
    collection_names: tuple[str, ...]
    role: str


@dataclass(frozen=True, slots=True)
class ObservationTimelineEntry:
    observation_public_id: str
    observed_at_us: int
    country_code: str | None
    notes: str | None
    photos: tuple[ObservationEvidencePhoto, ...]


@dataclass(frozen=True, slots=True)
class SpeciesObservationHistory:
    summary: SpeciesObservationSummary
    timeline: tuple[ObservationTimelineEntry, ...]


@dataclass(frozen=True, slots=True)
class LifeListEntry:
    group_name: str
    species_count: int
    observation_count: int
    evidence_photo_count: int


@dataclass(frozen=True, slots=True)
class ObservationStatistics:
    species_count: int
    observation_count: int
    evidence_photo_count: int
    country_count: int
    first_observations_this_year: int
    most_observed_species: tuple[SpeciesObservationSummary, ...]
    life_list: tuple[LifeListEntry, ...]
