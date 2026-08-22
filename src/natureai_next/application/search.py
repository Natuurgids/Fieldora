"""Application services for search, saved searches, collections, and geography."""

from __future__ import annotations

from natureai_next.domain.search import (
    Group,
    LogicalOperator,
    Predicate,
    PredicateOperator,
    StructuredAssetFilters,
    StructuredQuery,
    validate_query,
)
from natureai_next.ports.search import (
    CollectionPort,
    GeographyPort,
    LocationInput,
    SavedSearchPort,
    SearchPort,
    SearchRequest,
)


def _validate_iso_date(value: str) -> str:
    from datetime import date

    cleaned = value.strip()
    try:
        parsed = date.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError("capture date must use YYYY-MM-DD") from exc
    return parsed.isoformat()


class SearchService:
    def __init__(self, search: SearchPort) -> None:
        self._search = search

    def execute(self, request: SearchRequest):
        validate_query(request.query)
        return self._search.search(request)

    def suggestions(self, prefix: str, *, limit: int = 20):
        return self._search.suggestions(prefix, limit=limit)

    def rebuild_index(self) -> None:
        self._search.rebuild_fts()

    def index_parity(self) -> tuple[int, int]:
        return self._search.fts_parity()


class QuickSearchService:
    """Bounded catalog search combining quick text and structured filters."""

    def __init__(self, search: SearchPort) -> None:
        self._search = search

    def build_query(
        self,
        *,
        text: str = "",
        filters: StructuredAssetFilters | None = None,
        scope: str = "all",
    ) -> StructuredQuery:
        """Build the public structured query used by quick search and saved views."""
        cleaned = " ".join(text.split())
        active = filters or StructuredAssetFilters()
        predicates: list[Predicate] = []
        if cleaned:
            field = {
                "all": "text",
                "filename": "filename",
                "title": "title",
                "caption": "caption",
                "notes": "notes",
                "tags": "tag_text",
            }.get(scope)
            if field is None:
                raise ValueError("unsupported search scope")
            predicates.append(Predicate(field, PredicateOperator.CONTAINS, cleaned))
        if active.minimum_rating is not None:
            if not 0 <= active.minimum_rating <= 5:
                raise ValueError("minimum rating must be between 0 and 5")
            predicates.append(Predicate("rating", PredicateOperator.GTE, active.minimum_rating))
        if active.color_label is not None:
            predicates.append(Predicate("color_label", PredicateOperator.EQ, active.color_label))
        if active.pick_state is not None:
            predicates.append(Predicate("pick_state", PredicateOperator.EQ, active.pick_state))
        if active.captured_from_us is not None:
            predicates.append(
                Predicate("capture_time_utc_us", PredicateOperator.GTE, active.captured_from_us)
            )
        if active.captured_to_us is not None:
            predicates.append(
                Predicate("capture_time_utc_us", PredicateOperator.LTE, active.captured_to_us)
            )
        if (
            active.captured_from_us is not None
            and active.captured_to_us is not None
            and active.captured_from_us > active.captured_to_us
        ):
            raise ValueError("capture start must not be after capture end")
        if active.captured_from_date is not None:
            predicates.append(
                Predicate(
                    "capture_date",
                    PredicateOperator.GTE,
                    _validate_iso_date(active.captured_from_date),
                )
            )
        if active.captured_to_date is not None:
            predicates.append(
                Predicate(
                    "capture_date",
                    PredicateOperator.LTE,
                    _validate_iso_date(active.captured_to_date),
                )
            )
        if (
            active.captured_from_date is not None
            and active.captured_to_date is not None
            and active.captured_from_date > active.captured_to_date
        ):
            raise ValueError("capture start date must not be after capture end date")
        for field, value in (
            ("pixel_width", active.minimum_width),
            ("pixel_height", active.minimum_height),
        ):
            if value is not None:
                if value <= 0:
                    raise ValueError(f"{field} must be positive")
                predicates.append(Predicate(field, PredicateOperator.GTE, value))
        tag = active.tag.strip() if active.tag else ""
        if tag:
            predicates.append(Predicate("tag", PredicateOperator.EQ, tag))
        taxonomy_name = " ".join(active.taxonomy_name.split()) if active.taxonomy_name else ""
        if taxonomy_name:
            predicates.append(Predicate("taxon_name", PredicateOperator.CONTAINS, taxonomy_name))
        for field, value in (
            ("camera_make", active.camera_make),
            ("camera_model", active.camera_model),
            ("lens", active.lens),
        ):
            cleaned_value = " ".join(value.split()) if value else ""
            if cleaned_value:
                predicates.append(Predicate(field, PredicateOperator.CONTAINS, cleaned_value))
        bounds = (
            active.minimum_latitude,
            active.maximum_latitude,
            active.minimum_longitude,
            active.maximum_longitude,
        )
        if any(value is not None for value in bounds):
            if not all(value is not None for value in bounds):
                raise ValueError("GPS bounds require south, north, west, and east values")
            south, north, west, east = bounds
            assert south is not None and north is not None and west is not None and east is not None
            if not (-90 <= south <= north <= 90):
                raise ValueError("GPS latitude bounds must satisfy -90 <= south <= north <= 90")
            if not (-180 <= west <= east <= 180):
                raise ValueError("GPS longitude bounds must satisfy -180 <= west <= east <= 180")
            predicates.append(Predicate("latitude", PredicateOperator.BETWEEN, (south, north)))
            predicates.append(Predicate("longitude", PredicateOperator.BETWEEN, (west, east)))
        if active.exact_duplicates_only is True:
            predicates.append(Predicate("exact_duplicate", PredicateOperator.EQ, True))
        if not predicates:
            raise ValueError("search text or at least one filter is required")
        root = (
            predicates[0] if len(predicates) == 1 else Group(LogicalOperator.AND, tuple(predicates))
        )
        query = StructuredQuery(root)
        validate_query(query)
        return query

    def page(
        self,
        *,
        text: str = "",
        filters: StructuredAssetFilters | None = None,
        limit: int,
        after_id: int | None = None,
        scope: str = "all",
    ):
        query = self.build_query(text=text, filters=filters, scope=scope)
        return self._search.search(
            SearchRequest(query=query, limit=limit, after_id=after_id, sort="id_asc")
        )


class SavedSearchService:
    def __init__(self, store: SavedSearchPort) -> None:
        self._store = store

    def save(self, *, public_id: str, name: str, query: StructuredQuery, now_us: int):
        if not name.strip():
            raise ValueError("saved search name is required")
        validate_query(query)
        return self._store.save_search(
            public_id=public_id, name=name.strip(), query=query, now_us=now_us
        )

    def list(self):
        return self._store.list_saved_searches()

    def delete(self, public_id: str) -> None:
        self._store.delete_saved_search(public_id)


class CollectionService:
    def __init__(self, collections: CollectionPort) -> None:
        self._collections = collections

    def create_manual(self, **kwargs) -> None:
        self._collections.create_manual(**kwargs)

    def create_smart(self, **kwargs) -> None:
        validate_query(kwargs["query"])
        self._collections.create_smart(**kwargs)

    def add_assets(self, **kwargs) -> None:
        self._collections.add_assets(**kwargs)

    def list(self):
        return self._collections.list_collections()


class LibraryViewsService:
    """Application facade for reusable saved searches and manual collections."""

    def __init__(
        self, *, saved: SavedSearchPort, collections: CollectionPort, search: SearchPort, clock, ids
    ) -> None:
        self._saved = saved
        self._collections = collections
        self._search = search
        self._clock = clock
        self._ids = ids
        self._quick = QuickSearchService(search)

    def _now_us(self) -> int:
        return int(self._clock.now_utc().timestamp() * 1_000_000)

    def save_current_search(
        self, *, name: str, text: str, filters: StructuredAssetFilters
    ) -> object:
        cleaned_name = " ".join(name.split())
        if not cleaned_name:
            raise ValueError("saved search name is required")
        query = self._quick.build_query(text=text, filters=filters)
        return self._saved.save_search(
            public_id=str(self._ids.new_uuid()),
            name=cleaned_name,
            query=query,
            now_us=self._now_us(),
        )

    def list_saved_searches(self):
        return self._saved.list_saved_searches()

    def delete_saved_search(self, public_id: str) -> None:
        self._saved.delete_saved_search(public_id)

    def page_saved_search(self, *, public_id: str, limit: int, after_id: int | None = None):
        saved = next(
            (item for item in self._saved.list_saved_searches() if item.public_id == public_id),
            None,
        )
        if saved is None:
            raise KeyError(public_id)
        return self._search.search(
            SearchRequest(saved.query, limit=limit, after_id=after_id, sort="id_asc")
        )

    def create_smart_collection(
        self,
        *,
        name: str,
        text: str,
        filters: StructuredAssetFilters,
        description: str | None = None,
    ) -> None:
        cleaned_name = " ".join(name.split())
        if not cleaned_name:
            raise ValueError("collection name is required")
        query = self._quick.build_query(text=text, filters=filters)
        self._collections.create_smart(
            public_id=str(self._ids.new_uuid()),
            name=cleaned_name,
            description=(description.strip() or None) if description else None,
            parent_public_id=None,
            query=query,
            now_us=self._now_us(),
        )

    def create_manual_collection(self, *, name: str, description: str | None = None) -> None:
        cleaned_name = " ".join(name.split())
        if not cleaned_name:
            raise ValueError("collection name is required")
        self._collections.create_manual(
            public_id=str(self._ids.new_uuid()),
            name=cleaned_name,
            description=(description.strip() or None) if description else None,
            parent_public_id=None,
            now_us=self._now_us(),
        )

    def add_assets_to_collection(
        self, *, collection_public_id: str, asset_public_ids: tuple[str, ...]
    ) -> None:
        unique = tuple(dict.fromkeys(asset_public_ids))
        if not unique:
            raise ValueError("select at least one asset")
        self._collections.add_assets(
            collection_public_id=collection_public_id,
            asset_public_ids=unique,
            now_us=self._now_us(),
        )

    def remove_assets_from_collection(
        self, *, collection_public_id: str, asset_public_ids: tuple[str, ...]
    ) -> None:
        unique = tuple(dict.fromkeys(asset_public_ids))
        if not unique:
            raise ValueError("select at least one asset")
        self._collections.remove_assets(
            collection_public_id=collection_public_id,
            asset_public_ids=unique,
            now_us=self._now_us(),
        )

    def update_collection(
        self, *, public_id: str, name: str, description: str | None = None
    ) -> None:
        self._collections.update_collection(
            public_id=public_id, name=name, description=description, now_us=self._now_us()
        )

    def delete_collection(self, public_id: str) -> None:
        self._collections.delete_collection(public_id)

    def list_collections(self):
        return self._collections.list_collections()

    def page_collection(self, *, public_id: str, limit: int, after_id: int | None = None):
        query = self._collections.collection_query(public_id)
        if query is None:
            query = StructuredQuery(Predicate("collection", PredicateOperator.EQ, public_id))
        return self._search.search(
            SearchRequest(query, limit=limit, after_id=after_id, sort="id_asc")
        )


class GeographyService:
    def __init__(self, geography: GeographyPort) -> None:
        self._geography = geography

    def set_location(
        self,
        *,
        asset_public_id: str,
        location_public_id: str,
        location: LocationInput,
        role: str,
        now_us: int,
    ) -> None:
        self._geography.set_asset_location(
            asset_public_id=asset_public_id,
            location_public_id=location_public_id,
            location=location,
            role=role,
            now_us=now_us,
        )

    def nearby(self, *, latitude: float, longitude: float, radius_km: float, limit: int = 1000):
        return self._geography.assets_in_radius(
            latitude=latitude, longitude=longitude, radius_km=radius_km, limit=limit
        )
