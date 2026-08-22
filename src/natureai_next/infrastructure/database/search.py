"""SQLite structured search, FTS, collections, and geography adapters."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from natureai_next.domain.search import (
    Group,
    LogicalOperator,
    Not,
    Predicate,
    PredicateOperator,
    StructuredQuery,
    query_from_dict,
    query_to_dict,
    validate_query,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.unit_of_work import SqliteUnitOfWork
from natureai_next.ports.catalog_queries import AssetGridRow, AssetPage
from natureai_next.ports.search import CollectionSummary, LocationInput, SavedSearch, SearchRequest


@dataclass(frozen=True, slots=True)
class CompiledQuery:
    sql: str
    parameters: tuple[Any, ...]


_CAPTURE_DATE_SQL = """(CASE
    WHEN a.capture_time_utc_us IS NOT NULL THEN strftime('%Y-%m-%d', a.capture_time_utc_us / 1000000.0, 'unixepoch')
    WHEN a.capture_local_text GLOB '[0-9][0-9][0-9][0-9]:[0-9][0-9]:[0-9][0-9]*'
        THEN substr(a.capture_local_text,1,4) || '-' || substr(a.capture_local_text,6,2) || '-' || substr(a.capture_local_text,9,2)
    WHEN a.capture_local_text GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'
        THEN substr(a.capture_local_text,1,10)
    ELSE NULL
END)"""

_FIELD_SQL = {
    "rating": "a.rating",
    "color_label": "a.color_label",
    "pick_state": "a.pick_state",
    "capture_time_utc_us": "a.capture_time_utc_us",
    "capture_date": _CAPTURE_DATE_SQL,
    "availability_state": "f.availability_state",
    "storage_mode": "f.storage_mode",
    "pixel_width": "ip.pixel_width",
    "pixel_height": "ip.pixel_height",
    "country_code": "loc.country_code",
    "latitude": "loc.latitude",
    "longitude": "loc.longitude",
    "title": "a.title",
    "caption": "a.caption",
    "notes": "a.user_notes",
    "camera_make": "ip.camera_make",
    "camera_model": "ip.camera_model",
    "lens": "ip.lens",
    "filename": "f.normalized_path",
}


def _fts_prefix_query(value: object) -> str:
    terms = [term for term in re.split(r"\s+", str(value).strip()) if term]
    if not terms:
        raise ValueError("text search requires at least one term")
    return " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"*' for term in terms)


def _like_contains(value: object) -> str:
    escaped = str(value).casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _path_terms(value: object) -> tuple[str, ...]:
    """Return independent path-search terms.

    A user-facing filename search also covers directory names.  Treating the
    complete input as one LIKE value made ``holiday finch`` fail for a path
    such as ``Holiday/2026/finch.jpg``.
    """
    return tuple(term for term in re.split(r"[\s/\\]+", str(value).strip()) if term)


def compile_query(query: StructuredQuery) -> CompiledQuery:
    validate_query(query)
    params: list[Any] = []

    def compile_node(node: Predicate | Not | Group) -> str:
        if isinstance(node, Group):
            joiner = " AND " if node.operator is LogicalOperator.AND else " OR "
            return "(" + joiner.join(compile_node(x) for x in node.children) + ")"
        if isinstance(node, Not):
            return "(NOT " + compile_node(node.child) + ")"
        field, op, value = node.field, node.operator, node.value
        if field == "tag":
            if op is PredicateOperator.EXISTS:
                return "EXISTS(SELECT 1 FROM asset_tags atx WHERE atx.asset_id=a.id)"
            values = value if op is PredicateOperator.IN else [value]
            placeholders = ",".join("?" for _ in values)
            params.extend(str(x).casefold() for x in values)
            expression = f"EXISTS(SELECT 1 FROM asset_tags atx JOIN tags tx ON tx.id=atx.tag_id WHERE atx.asset_id=a.id AND tx.normalized_name IN ({placeholders}))"
            return f"NOT ({expression})" if op is PredicateOperator.NE else expression
        if field == "exact_duplicate":
            expression = """EXISTS(
                SELECT 1 FROM file_instances d1
                JOIN file_instances d2 ON d2.sha256=d1.sha256 AND d2.id!=d1.id
                WHERE d1.asset_id=a.id AND d1.sha256 IS NOT NULL
                AND d1.availability_state!='missing' AND d2.availability_state!='missing'
            )"""
            return expression if bool(value) else f"NOT ({expression})"
        if field == "collection":
            values = value if op is PredicateOperator.IN else [value]
            placeholders = ",".join("?" for _ in values)
            params.extend(values)
            expression = f"EXISTS(SELECT 1 FROM collection_assets cax JOIN collections cx ON cx.id=cax.collection_id WHERE cax.asset_id=a.id AND cx.public_id IN ({placeholders}))"
            return f"NOT ({expression})" if op is PredicateOperator.NE else expression
        if field == "taxon_public_id":
            values = value if op is PredicateOperator.IN else [value]
            placeholders = ",".join("?" for _ in values)
            params.extend(values)
            expression = f"EXISTS(SELECT 1 FROM observations ox JOIN taxa tax ON tax.id=ox.taxon_id WHERE ox.asset_id=a.id AND tax.public_id IN ({placeholders}))"
            return f"NOT ({expression})" if op is PredicateOperator.NE else expression
        if field == "taxon_name":
            pattern = _like_contains(value)
            params.extend((pattern, pattern, pattern, pattern, pattern, pattern))
            return """(
                EXISTS(
                    SELECT 1 FROM observations ox
                    LEFT JOIN taxa tax ON tax.id=ox.taxon_id
                    LEFT JOIN taxon_names txn ON txn.taxon_id=tax.id
                    LEFT JOIN user_taxa utx ON utx.id=ox.user_taxon_id
                    WHERE ox.asset_id=a.id AND (
                        lower(COALESCE(tax.scientific_name,'')) LIKE ? ESCAPE '\\' OR
                        lower(COALESCE(txn.name,'')) LIKE ? ESCAPE '\\' OR
                        lower(COALESCE(utx.display_name,'')) LIKE ? ESCAPE '\\' OR
                        lower(COALESCE(utx.scientific_name,'')) LIKE ? ESCAPE '\\'
                    )
                ) OR EXISTS(
                    SELECT 1 FROM asset_taxonomy_enrichments ate
                    WHERE ate.asset_id=a.id AND (
                        lower(COALESCE(ate.scientific_name,'')) LIKE ? ESCAPE '\\' OR
                        lower(COALESCE(ate.vernacular_name,'')) LIKE ? ESCAPE '\\'
                    )
                )
            )"""
        if field == "text":
            terms = _path_terms(value)
            path_sql = " AND ".join(
                "(lower(COALESCE(f.normalized_path,'')) LIKE ? ESCAPE '\\' OR "
                "lower(COALESCE(f.import_source_path,'')) LIKE ? ESCAPE '\\')"
                for _ in terms
            )
            params.append(_fts_prefix_query(value))
            for term in terms:
                pattern = _like_contains(term)
                params.extend((pattern, pattern))
            return (
                "(a.id IN (SELECT rowid FROM asset_search_fts "
                f"WHERE asset_search_fts MATCH ?) OR ({path_sql}))"
            )
        if field == "tag_text":
            params.append(_like_contains(value))
            return "EXISTS(SELECT 1 FROM asset_tags atx JOIN tags tx ON tx.id=atx.tag_id WHERE atx.asset_id=a.id AND lower(tx.name) LIKE ? ESCAPE '\\')"
        if field == "filename":
            terms = _path_terms(value)
            for term in terms:
                pattern = _like_contains(term)
                params.extend((pattern, pattern))
            return "(" + " AND ".join(
                "(lower(COALESCE(f.normalized_path,'')) LIKE ? ESCAPE '\\' OR "
                "lower(COALESCE(f.import_source_path,'')) LIKE ? ESCAPE '\\')"
                for _ in terms
            ) + ")"
        column = _FIELD_SQL[field]
        if op is PredicateOperator.EXISTS:
            return f"{column} IS NOT NULL" if value is not False else f"{column} IS NULL"
        if op is PredicateOperator.BETWEEN:
            params.extend(value)
            return f"{column} BETWEEN ? AND ?"
        if op is PredicateOperator.IN:
            params.extend(value)
            return f"{column} IN ({','.join('?' for _ in value)})"
        if op is PredicateOperator.CONTAINS:
            params.append(_like_contains(value))
            return f"lower(COALESCE({column},'')) LIKE ? ESCAPE '\\'"
        symbols = {
            PredicateOperator.EQ: "=",
            PredicateOperator.NE: "!=",
            PredicateOperator.LT: "<",
            PredicateOperator.LTE: "<=",
            PredicateOperator.GT: ">",
            PredicateOperator.GTE: ">=",
        }
        params.append(value)
        return f"{column} {symbols[op]} ?"

    return CompiledQuery(compile_node(query.root), tuple(params))


class SqliteSearchAdapter:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def search(self, request: SearchRequest) -> AssetPage:
        if not 1 <= request.limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        compiled = compile_query(request.query)
        sort_sql = {
            "id_asc": "a.id ASC",
            "capture_desc": "a.capture_time_utc_us DESC,a.id DESC",
            "rating_desc": "a.rating DESC,a.id ASC",
        }.get(request.sort)
        if sort_sql is None:
            raise ValueError("unsupported sort")
        cursor_clause = (
            " AND a.id>?" if request.sort == "id_asc" and request.after_id is not None else ""
        )
        params = list(compiled.parameters)
        if cursor_clause:
            params.append(request.after_id)
        params.append(request.limit)
        joins = "LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id LEFT JOIN image_properties ip ON ip.asset_id=a.id LEFT JOIN asset_locations al ON al.asset_id=a.id AND al.role='capture' LEFT JOIN locations loc ON loc.id=al.location_id"
        base_without_cursor = (
            f"FROM assets a {joins} WHERE a.lifecycle_state='active' AND {compiled.sql}"
        )
        base = f"{base_without_cursor}{cursor_clause}"
        c = self._factory.connect()
        try:
            rows = c.execute(
                f"""SELECT DISTINCT a.id,a.public_id,a.revision,a.title,a.rating,a.color_label,a.pick_state,a.capture_time_utc_us,
                f.public_id file_public_id,f.normalized_path,ip.pixel_width,ip.pixel_height,
                (SELECT d.relative_path FROM derivative_cache_entries d WHERE d.source_file_instance_id=f.id AND d.derivative_kind='thumbnail' AND d.state='valid' ORDER BY d.created_at_us DESC LIMIT 1) thumbnail_path
                {base} ORDER BY {sort_sql} LIMIT ?""",
                params,
            ).fetchall()
            total = int(
                c.execute(
                    f"SELECT COUNT(DISTINCT a.id) {base_without_cursor}", compiled.parameters
                ).fetchone()[0]
            )
            projected = tuple(
                AssetGridRow(
                    public_id=r["public_id"],
                    internal_id=r["id"],
                    revision=r["revision"],
                    title=r["title"],
                    rating=r["rating"],
                    color_label=r["color_label"],
                    pick_state=r["pick_state"],
                    capture_time_utc_us=r["capture_time_utc_us"],
                    primary_file_public_id=r["file_public_id"],
                    primary_path=r["normalized_path"],
                    thumbnail_path=r["thumbnail_path"],
                    pixel_width=r["pixel_width"],
                    pixel_height=r["pixel_height"],
                )
                for r in rows
            )
            return AssetPage(
                projected,
                projected[-1].internal_id
                if request.sort == "id_asc" and len(projected) == request.limit
                else None,
                total,
            )
        finally:
            c.close()

    def suggestions(self, prefix: str, *, limit: int = 20) -> tuple[str, ...]:
        if not prefix.strip():
            return ()
        q = prefix.casefold() + "%"
        c = self._factory.connect()
        try:
            rows = c.execute(
                "SELECT display_name value FROM tags WHERE normalized_name LIKE ? UNION SELECT scientific_name FROM taxa WHERE lower(scientific_name) LIKE ? UNION SELECT scientific_name FROM asset_taxonomy_enrichments WHERE lower(scientific_name) LIKE ? UNION SELECT COALESCE(place_name,locality) FROM locations WHERE lower(COALESCE(place_name,locality,'')) LIKE ? ORDER BY value LIMIT ?",
                (q, q, q, q, limit),
            ).fetchall()
            return tuple(str(r[0]) for r in rows if r[0])
        finally:
            c.close()

    def rebuild_fts(self) -> None:
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            u.connection.execute("DELETE FROM asset_search_fts")
            u.connection.execute(
                "INSERT INTO asset_search_fts(rowid,asset_public_id,title,caption,user_notes,tags) SELECT a.id,a.public_id,COALESCE(a.title,''),COALESCE(a.caption,''),COALESCE(a.user_notes,''),COALESCE((SELECT group_concat(t.display_name,' ') FROM asset_tags x JOIN tags t ON t.id=x.tag_id WHERE x.asset_id=a.id),'') FROM assets a"
            )
            u.commit()

    def fts_parity(self) -> tuple[int, int]:
        c = self._factory.connect()
        try:
            return int(c.execute("SELECT COUNT(*) FROM assets").fetchone()[0]), int(
                c.execute("SELECT COUNT(*) FROM asset_search_fts").fetchone()[0]
            )
        finally:
            c.close()


class SqliteSavedSearchAdapter:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def save_search(
        self, *, public_id: str, name: str, query: StructuredQuery, now_us: int
    ) -> SavedSearch:
        validate_query(query)
        payload = json.dumps(query_to_dict(query), separators=(",", ":"), sort_keys=True)
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            u.connection.execute(
                "INSERT INTO saved_searches(public_id,name,query_json,query_schema_version,created_at_us,modified_at_us) VALUES(?,?,?,?,?,?) ON CONFLICT(public_id) DO UPDATE SET name=excluded.name,query_json=excluded.query_json,query_schema_version=excluded.query_schema_version,modified_at_us=excluded.modified_at_us",
                (public_id, name, payload, query.schema_version, now_us, now_us),
            )
            u.commit()
        return SavedSearch(public_id, name, query, now_us, now_us)

    def list_saved_searches(self) -> tuple[SavedSearch, ...]:
        c = self._factory.connect()
        try:
            return tuple(
                SavedSearch(
                    r["public_id"],
                    r["name"],
                    query_from_dict(json.loads(r["query_json"])),
                    r["created_at_us"],
                    r["modified_at_us"],
                )
                for r in c.execute("SELECT * FROM saved_searches ORDER BY name")
            )
        finally:
            c.close()

    def delete_saved_search(self, public_id: str) -> None:
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            u.connection.execute("DELETE FROM saved_searches WHERE public_id=?", (public_id,))
            u.commit()


class SqliteCollectionAdapter:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def _create(
        self,
        *,
        public_id: str,
        name: str,
        description: str | None,
        parent_public_id: str | None,
        kind: str,
        query: StructuredQuery | None,
        now_us: int,
    ) -> None:
        payload = (
            json.dumps(query_to_dict(query), separators=(",", ":"), sort_keys=True)
            if query
            else None
        )
        parent_sql = (
            "(SELECT id FROM collections WHERE public_id=?)" if parent_public_id else "NULL"
        )
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            u.connection.execute(
                f"INSERT INTO collections(public_id,collection_type,name,description,smart_query_json,query_schema_version,sort_mode,created_at_us,modified_at_us,parent_collection_id,position_key) VALUES(?,?,?,?,?,?, 'manual',?,?,{parent_sql},?)",
                (
                    public_id,
                    kind,
                    name,
                    description,
                    payload,
                    query.schema_version if query else None,
                    now_us,
                    now_us,
                    *((parent_public_id,) if parent_public_id else ()),
                    name.casefold(),
                ),
            )
            u.commit()

    def create_manual(self, **kw: Any) -> None:
        self._create(kind="manual", query=None, **kw)

    def create_smart(self, *, query: StructuredQuery, **kw: Any) -> None:
        validate_query(query)
        self._create(kind="smart", query=query, **kw)

    def add_assets(
        self, *, collection_public_id: str, asset_public_ids: tuple[str, ...], now_us: int
    ) -> None:
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            row = u.connection.execute(
                "SELECT id,collection_type FROM collections WHERE public_id=?",
                (collection_public_id,),
            ).fetchone()
            if row is None:
                raise KeyError(collection_public_id)
            if row["collection_type"] != "manual":
                raise ValueError("smart collections cannot have manual members")
            for i, pid in enumerate(asset_public_ids):
                u.connection.execute(
                    "INSERT OR IGNORE INTO collection_assets(collection_id,asset_id,position_key,added_at_us) SELECT ?,id,?,? FROM assets WHERE public_id=?",
                    (row["id"], f"{now_us:020d}:{i:08d}", now_us, pid),
                )
            u.commit()

    def remove_assets(
        self, *, collection_public_id: str, asset_public_ids: tuple[str, ...], now_us: int
    ) -> None:
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            row = u.connection.execute(
                "SELECT id,collection_type FROM collections WHERE public_id=?",
                (collection_public_id,),
            ).fetchone()
            if row is None:
                raise KeyError(collection_public_id)
            if row["collection_type"] != "manual":
                raise ValueError("smart collections cannot have manual members")
            if asset_public_ids:
                marks = ",".join("?" for _ in asset_public_ids)
                u.connection.execute(
                    f"DELETE FROM collection_assets WHERE collection_id=? AND asset_id IN (SELECT id FROM assets WHERE public_id IN ({marks}))",
                    (row["id"], *asset_public_ids),
                )
            u.connection.execute(
                "UPDATE collections SET modified_at_us=? WHERE id=?", (now_us, row["id"])
            )
            u.commit()

    def update_collection(
        self, *, public_id: str, name: str, description: str | None, now_us: int
    ) -> None:
        cleaned = " ".join(name.split())
        if not cleaned:
            raise ValueError("collection name is required")
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            cur = u.connection.execute(
                "UPDATE collections SET name=?,description=?,position_key=?,modified_at_us=? WHERE public_id=?",
                (
                    cleaned,
                    description.strip() or None if description else None,
                    cleaned.casefold(),
                    now_us,
                    public_id,
                ),
            )
            if cur.rowcount != 1:
                raise KeyError(public_id)
            u.commit()

    def delete_collection(self, public_id: str) -> None:
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            cur = u.connection.execute("DELETE FROM collections WHERE public_id=?", (public_id,))
            if cur.rowcount != 1:
                raise KeyError(public_id)
            u.commit()

    def collection_query(self, public_id: str) -> StructuredQuery | None:
        c = self._factory.connect(read_only=True)
        try:
            row = c.execute(
                "SELECT collection_type,smart_query_json FROM collections WHERE public_id=?",
                (public_id,),
            ).fetchone()
            if row is None:
                raise KeyError(public_id)
            if row["collection_type"] != "smart":
                return None
            return query_from_dict(json.loads(row["smart_query_json"]))
        finally:
            c.close()

    def list_collections(self) -> tuple[CollectionSummary, ...]:
        c = self._factory.connect()
        try:
            return tuple(
                CollectionSummary(
                    r["public_id"],
                    r["collection_type"],
                    r["name"],
                    r["description"],
                    r["parent_public_id"],
                    r["asset_count"],
                )
                for r in c.execute(
                    "SELECT c.public_id,c.collection_type,c.name,c.description,p.public_id parent_public_id,COUNT(ca.asset_id) asset_count FROM collections c LEFT JOIN collections p ON p.id=c.parent_collection_id LEFT JOIN collection_assets ca ON ca.collection_id=c.id GROUP BY c.id ORDER BY c.position_key,c.name"
                )
            )
        finally:
            c.close()


class SqliteGeographyAdapter:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def set_asset_location(
        self,
        *,
        asset_public_id: str,
        location_public_id: str,
        location: LocationInput,
        role: str,
        now_us: int,
    ) -> None:
        if not -90 <= location.latitude <= 90 or not -180 <= location.longitude <= 180:
            raise ValueError("invalid coordinates")
        if location.accuracy_m is not None and location.accuracy_m < 0:
            raise ValueError("invalid accuracy")
        if role not in {"capture", "subject", "user_defined"}:
            raise ValueError("invalid location role")
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            u.connection.execute(
                "INSERT INTO locations(public_id,latitude,longitude,altitude_m,accuracy_m,country_code,locality,place_name,source,created_at_us) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    location_public_id,
                    location.latitude,
                    location.longitude,
                    location.altitude_m,
                    location.accuracy_m,
                    location.country_code,
                    location.locality,
                    location.place_name,
                    location.source,
                    now_us,
                ),
            )
            u.connection.execute(
                "DELETE FROM asset_locations WHERE asset_id=(SELECT id FROM assets WHERE public_id=?) AND role=?",
                (asset_public_id, role),
            )
            u.connection.execute(
                "INSERT INTO asset_locations(asset_id,location_id,role,precedence) SELECT a.id,l.id,?,0 FROM assets a,locations l WHERE a.public_id=? AND l.public_id=?",
                (role, asset_public_id, location_public_id),
            )
            u.commit()

    def assets_in_radius(
        self, *, latitude: float, longitude: float, radius_km: float, limit: int = 1000
    ) -> tuple[str, ...]:
        if radius_km <= 0 or limit < 1:
            raise ValueError("radius and limit must be positive")
        lat_delta = radius_km / 111.32
        lon_delta = radius_km / (111.32 * max(0.01, math.cos(math.radians(latitude))))
        c = self._factory.connect()
        try:
            rows = c.execute(
                "SELECT a.public_id,l.latitude,l.longitude FROM location_rtree r JOIN locations l ON l.id=r.id JOIN asset_locations al ON al.location_id=l.id JOIN assets a ON a.id=al.asset_id WHERE r.min_lat BETWEEN ? AND ? AND r.min_lon BETWEEN ? AND ? AND a.lifecycle_state='active' LIMIT ?",
                (
                    latitude - lat_delta,
                    latitude + lat_delta,
                    longitude - lon_delta,
                    longitude + lon_delta,
                    limit * 4,
                ),
            ).fetchall()

            def distance(r: sqlite3.Row) -> float:
                p1, p2 = math.radians(latitude), math.radians(r["latitude"])
                dp = p2 - p1
                dl = math.radians(r["longitude"] - longitude)
                h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
                return 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))

            return tuple(
                r["public_id"]
                for r in sorted((x for x in rows if distance(x) <= radius_km), key=distance)[:limit]
            )
        finally:
            c.close()
