"""Taxonomy package, catalog, observation, and user-taxon ports."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from natureai_next.domain.taxonomy import (
    ObservationDraft,
    ObservationView,
    RegionOfInterestDraft,
    TaxonomyPackageData,
    TaxonPage,
    TaxonSummary,
)


class TaxonomyPackageVerifier(Protocol):
    def verify(self, path: Path) -> TaxonomyPackageData: ...


class TaxonomyCatalogPort(Protocol):
    def install(self, package: TaxonomyPackageData, *, now_us: int) -> str: ...
    def active_sources(self) -> tuple[dict[str, object], ...]: ...
    def search(
        self,
        text: str,
        *,
        language_tag: str | None = None,
        region_code: str | None = None,
        limit: int = 50,
    ) -> tuple[TaxonSummary, ...]: ...
    def children(
        self,
        parent_public_id: str | None,
        *,
        region_code: str | None = None,
        language_tag: str | None = None,
        after_name: str | None = None,
        limit: int = 200,
    ) -> TaxonPage: ...
    def detail(
        self, public_id: str, *, language_tag: str | None = None, region_code: str | None = None
    ) -> TaxonSummary: ...
    def verify_closure(self, source_public_id: str) -> tuple[int, int]: ...
    def rebuild_closure(self, source_public_id: str) -> None: ...


class ObservationPort(Protocol):
    def create(
        self,
        *,
        public_id: str,
        asset_public_id: str,
        draft: ObservationDraft,
        now_us: int,
        source: str = "user",
    ) -> ObservationView: ...
    def update(
        self, *, public_id: str, expected_revision: int, draft: ObservationDraft, now_us: int
    ) -> ObservationView: ...
    def list_for_asset(self, asset_public_id: str) -> tuple[ObservationView, ...]: ...
    def create_roi(
        self, *, public_id: str, asset_public_id: str, draft: RegionOfInterestDraft, now_us: int
    ) -> str: ...


class UserTaxonPort(Protocol):
    def create(
        self,
        *,
        public_id: str,
        display_name: str,
        scientific_name: str | None,
        rank: str | None,
        now_us: int,
    ) -> None: ...
    def map_to_taxon(
        self, *, user_taxon_public_id: str, taxon_public_id: str | None, now_us: int
    ) -> None: ...
