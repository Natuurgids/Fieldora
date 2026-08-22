"""Stable ports used by catalog presentation and editing services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AssetGridRow:
    public_id: str
    internal_id: int
    revision: int
    title: str | None
    rating: int | None
    color_label: str | None
    pick_state: str | None
    capture_time_utc_us: int | None
    primary_file_public_id: str | None
    primary_path: str | None
    thumbnail_path: str | None
    pixel_width: int | None
    pixel_height: int | None


@dataclass(frozen=True, slots=True)
class AssetDetail:
    public_id: str
    revision: int
    title: str | None
    caption: str | None
    user_notes: str | None
    rating: int | None
    color_label: str | None
    pick_state: str | None
    primary_path: str | None
    mime_type: str | None
    format_name: str | None
    pixel_width: int | None
    pixel_height: int | None
    tags: tuple[str, ...]
    capture_latitude: float | None = None
    capture_longitude: float | None = None
    capture_place_name: str | None = None
    subject_latitude: float | None = None
    subject_longitude: float | None = None
    subject_place_name: str | None = None
    storage_mode: str | None = None
    availability_state: str | None = None
    source_path: str | None = None
    aperture_master_path: str | None = None


@dataclass(frozen=True, slots=True)
class AssetPage:
    rows: tuple[AssetGridRow, ...]
    next_cursor: int | None
    total_count: int


@dataclass(frozen=True, slots=True)
class MetadataPatch:
    title: str | None
    caption: str | None
    user_notes: str | None
    rating: int | None
    color_label: str | None
    pick_state: str | None


@dataclass(frozen=True, slots=True)
class MetadataChangeResult:
    public_id: str
    previous_revision: int
    new_revision: int
    before: MetadataPatch
    after: MetadataPatch


@dataclass(frozen=True, slots=True)
class BatchReviewTarget:
    public_id: str
    expected_revision: int


@dataclass(frozen=True, slots=True)
class ReviewPatch:
    rating: int | None
    color_label: str | None
    pick_state: str | None
    update_rating: bool = True
    update_color_label: bool = True
    update_pick_state: bool = True


@dataclass(frozen=True, slots=True)
class BatchReviewResult:
    public_id: str
    previous_revision: int
    new_revision: int


class CatalogReadPort(Protocol):
    def page_assets(self, *, limit: int, after_id: int | None = None) -> AssetPage: ...
    def page_assets_by_public_ids(self, public_ids: tuple[str, ...]) -> AssetPage: ...
    def get_asset_detail(self, public_id: str) -> AssetDetail | None: ...
    def derivative_path(self, public_id: str, kind: str) -> str | None: ...


class CatalogEditPort(Protocol):
    def update_metadata(
        self, *, public_id: str, expected_revision: int, patch: MetadataPatch, modified_at_us: int
    ) -> MetadataChangeResult: ...
    def update_metadata_and_tags(
        self,
        *,
        public_id: str,
        expected_revision: int,
        patch: MetadataPatch,
        tag_names: tuple[str, ...],
        modified_at_us: int,
    ) -> MetadataChangeResult: ...
    def set_tags(
        self, *, public_ids: tuple[str, ...], tag_names: tuple[str, ...], modified_at_us: int
    ) -> None: ...
    def update_subject_location(
        self,
        *,
        public_id: str,
        latitude: float | None,
        longitude: float | None,
        place_name: str | None,
        modified_at_us: int,
    ) -> None: ...
    def update_review_batch(
        self,
        *,
        targets: tuple[BatchReviewTarget, ...],
        patch: ReviewPatch,
        modified_at_us: int,
    ) -> tuple[BatchReviewResult, ...]: ...
