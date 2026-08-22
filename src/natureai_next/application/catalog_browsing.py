"""Application services for paged catalog reads and metadata commands."""

from __future__ import annotations

from dataclasses import dataclass

from natureai_next.ports.catalog_queries import (
    AssetDetail,
    AssetPage,
    BatchReviewResult,
    BatchReviewTarget,
    CatalogEditPort,
    CatalogReadPort,
    MetadataChangeResult,
    MetadataPatch,
    ReviewPatch,
)
from natureai_next.ports.clock import Clock


class CatalogQueryService:
    def __init__(self, reader: CatalogReadPort) -> None:
        self._reader = reader

    def page(self, *, limit: int, after_id: int | None = None) -> AssetPage:
        if not 1 <= limit <= 500:
            raise ValueError("page limit must be between 1 and 500")
        return self._reader.page_assets(limit=limit, after_id=after_id)

    def by_public_ids(self, public_ids: tuple[str, ...]) -> AssetPage:
        return self._reader.page_assets_by_public_ids(public_ids)

    def detail(self, public_id: str) -> AssetDetail | None:
        return self._reader.get_asset_detail(public_id)

    def derivative_path(self, public_id: str, kind: str) -> str | None:
        if not kind.strip():
            raise ValueError("derivative kind is required")
        return self._reader.derivative_path(public_id, kind.strip())


@dataclass(frozen=True, slots=True)
class UndoableMetadataCommand:
    change: MetadataChangeResult


class CatalogEditService:
    def __init__(self, editor: CatalogEditPort, clock: Clock) -> None:
        self._editor, self._clock = editor, clock

    @staticmethod
    def _clean_tags(tag_names: tuple[str, ...]) -> tuple[str, ...]:
        unique: dict[str, str] = {}
        for raw_name in tag_names:
            name = raw_name.strip()
            if name:
                unique.setdefault(name.casefold(), name)
        return tuple(sorted(unique.values(), key=str.casefold))

    def update(
        self, *, public_id: str, expected_revision: int, patch: MetadataPatch
    ) -> UndoableMetadataCommand:
        now = int(self._clock.now_utc().timestamp() * 1_000_000)
        return UndoableMetadataCommand(
            self._editor.update_metadata(
                public_id=public_id,
                expected_revision=expected_revision,
                patch=patch,
                modified_at_us=now,
            )
        )

    def update_with_tags(
        self,
        *,
        public_id: str,
        expected_revision: int,
        patch: MetadataPatch,
        tag_names: tuple[str, ...],
    ) -> UndoableMetadataCommand:
        clean = self._clean_tags(tag_names)
        now = int(self._clock.now_utc().timestamp() * 1_000_000)
        return UndoableMetadataCommand(
            self._editor.update_metadata_and_tags(
                public_id=public_id,
                expected_revision=expected_revision,
                patch=patch,
                tag_names=clean,
                modified_at_us=now,
            )
        )

    def update_subject_location(
        self,
        *,
        public_id: str,
        latitude: float | None,
        longitude: float | None,
        place_name: str | None,
    ) -> None:
        if (latitude is None) != (longitude is None):
            raise ValueError("subject latitude and longitude must be supplied together")
        if latitude is not None and not -90 <= latitude <= 90:
            raise ValueError("subject latitude must be between -90 and 90")
        if longitude is not None and not -180 <= longitude <= 180:
            raise ValueError("subject longitude must be between -180 and 180")
        clean_name = place_name.strip() if place_name else None
        now = int(self._clock.now_utc().timestamp() * 1_000_000)
        self._editor.update_subject_location(
            public_id=public_id,
            latitude=latitude,
            longitude=longitude,
            place_name=clean_name,
            modified_at_us=now,
        )

    def apply_tags(self, *, public_ids: tuple[str, ...], tag_names: tuple[str, ...]) -> None:
        clean = self._clean_tags(tag_names)
        now = int(self._clock.now_utc().timestamp() * 1_000_000)
        self._editor.set_tags(public_ids=public_ids, tag_names=clean, modified_at_us=now)

    def update_review_batch(
        self,
        *,
        targets: tuple[BatchReviewTarget, ...],
        patch: ReviewPatch,
    ) -> tuple[BatchReviewResult, ...]:
        if not targets:
            raise ValueError("batch review requires at least one asset")
        if len(targets) > 500:
            raise ValueError("batch review is limited to 500 assets")
        public_ids = tuple(target.public_id.strip() for target in targets)
        if any(not public_id for public_id in public_ids):
            raise ValueError("batch review asset IDs must not be blank")
        if len(set(public_ids)) != len(public_ids):
            raise ValueError("batch review contains duplicate assets")
        if any(target.expected_revision < 1 for target in targets):
            raise ValueError("expected revisions must be positive")
        if patch.rating is not None and not 0 <= patch.rating <= 5:
            raise ValueError("rating must be between 0 and 5")
        if patch.pick_state not in {None, "pick", "reject"}:
            raise ValueError("pick state must be pick, reject, or unset")
        if patch.color_label is not None and not patch.color_label.strip():
            raise ValueError("color label must not be blank")
        if not (patch.update_rating or patch.update_color_label or patch.update_pick_state):
            raise ValueError("batch review requires at least one changed field")
        now = int(self._clock.now_utc().timestamp() * 1_000_000)
        normalized = tuple(
            BatchReviewTarget(public_id, target.expected_revision)
            for public_id, target in zip(public_ids, targets, strict=False)
        )
        clean_patch = ReviewPatch(
            patch.rating,
            patch.color_label.strip() if patch.color_label is not None else None,
            patch.pick_state,
            patch.update_rating,
            patch.update_color_label,
            patch.update_pick_state,
        )
        return self._editor.update_review_batch(
            targets=normalized, patch=clean_patch, modified_at_us=now
        )
