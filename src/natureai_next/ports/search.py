"""Search, collection, and geography ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from natureai_next.domain.search import StructuredQuery
from natureai_next.ports.catalog_queries import AssetPage


@dataclass(frozen=True, slots=True)
class SearchRequest:
    query: StructuredQuery
    limit: int = 200
    after_id: int | None = None
    sort: str = "id_asc"


@dataclass(frozen=True, slots=True)
class SavedSearch:
    public_id: str
    name: str
    query: StructuredQuery
    created_at_us: int
    modified_at_us: int


@dataclass(frozen=True, slots=True)
class CollectionSummary:
    public_id: str
    collection_type: str
    name: str
    description: str | None
    parent_public_id: str | None
    asset_count: int


@dataclass(frozen=True, slots=True)
class LocationInput:
    latitude: float
    longitude: float
    altitude_m: float | None = None
    accuracy_m: float | None = None
    country_code: str | None = None
    locality: str | None = None
    place_name: str | None = None
    source: str = "user"


class SearchPort(Protocol):
    def search(self, request: SearchRequest) -> AssetPage: ...
    def suggestions(self, prefix: str, *, limit: int = 20) -> tuple[str, ...]: ...
    def rebuild_fts(self) -> None: ...
    def fts_parity(self) -> tuple[int, int]: ...


class SavedSearchPort(Protocol):
    def save_search(
        self, *, public_id: str, name: str, query: StructuredQuery, now_us: int
    ) -> SavedSearch: ...
    def list_saved_searches(self) -> tuple[SavedSearch, ...]: ...
    def delete_saved_search(self, public_id: str) -> None: ...


class CollectionPort(Protocol):
    def create_manual(
        self,
        *,
        public_id: str,
        name: str,
        description: str | None,
        parent_public_id: str | None,
        now_us: int,
    ) -> None: ...
    def create_smart(
        self,
        *,
        public_id: str,
        name: str,
        description: str | None,
        parent_public_id: str | None,
        query: StructuredQuery,
        now_us: int,
    ) -> None: ...
    def add_assets(
        self, *, collection_public_id: str, asset_public_ids: tuple[str, ...], now_us: int
    ) -> None: ...
    def remove_assets(
        self, *, collection_public_id: str, asset_public_ids: tuple[str, ...], now_us: int
    ) -> None: ...
    def update_collection(
        self, *, public_id: str, name: str, description: str | None, now_us: int
    ) -> None: ...
    def delete_collection(self, public_id: str) -> None: ...
    def collection_query(self, public_id: str) -> StructuredQuery | None: ...
    def list_collections(self) -> tuple[CollectionSummary, ...]: ...


class GeographyPort(Protocol):
    def set_asset_location(
        self,
        *,
        asset_public_id: str,
        location_public_id: str,
        location: LocationInput,
        role: str,
        now_us: int,
    ) -> None: ...
    def assets_in_radius(
        self, *, latitude: float, longitude: float, radius_km: float, limit: int = 1000
    ) -> tuple[str, ...]: ...
