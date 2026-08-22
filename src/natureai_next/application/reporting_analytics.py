"""Read-only analytics projections for the Aperture reporting workspace."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


@dataclass(frozen=True, slots=True)
class AnalyticsFilters:
    asset_public_ids: tuple[str, ...] | None = None
    media_type: str = "All"
    taxon_group: str = "All"
    country: str = "All"
    region: str = "All"
    review_state: str = "All"
    date_from: str = ""
    date_to: str = ""


@dataclass(frozen=True, slots=True)
class AnalyticsSnapshot:
    asset_count: int
    observation_count: int
    identified_count: int
    confirmed_count: int
    media_assets: tuple[tuple[str, int], ...]
    identified_by_media: tuple[tuple[str, int], ...]
    observations_by_group: tuple[tuple[str, int], ...]
    observations_by_country: tuple[tuple[str, int], ...]
    observations_by_region: tuple[tuple[str, int], ...]
    observations_by_month: tuple[tuple[str, int], ...]
    review_states: tuple[tuple[str, int], ...]


class ReportingAnalyticsReader:
    """Build compact aggregates without changing library data."""

    MEDIA_CASE = """CASE
      WHEN lower(COALESCE(f.mime_type,'')) LIKE 'image/%' THEN 'Photos'
      WHEN lower(COALESCE(f.mime_type,'')) LIKE 'video/%' THEN 'Videos'
      WHEN lower(COALESCE(f.mime_type,'')) LIKE 'audio/%' THEN 'Sounds'
      WHEN lower(COALESCE(f.mime_type,'')) IN ('application/pdf','application/msword','application/vnd.openxmlformats-officedocument.wordprocessingml.document','text/plain','application/rtf') THEN 'Documents'
      WHEN lower(COALESCE(f.normalized_path,'')) GLOB '*.mp4' OR lower(COALESCE(f.normalized_path,'')) GLOB '*.mov' OR lower(COALESCE(f.normalized_path,'')) GLOB '*.mkv' THEN 'Videos'
      WHEN lower(COALESCE(f.normalized_path,'')) GLOB '*.wav' OR lower(COALESCE(f.normalized_path,'')) GLOB '*.flac' OR lower(COALESCE(f.normalized_path,'')) GLOB '*.mp3' THEN 'Sounds'
      WHEN lower(COALESCE(f.normalized_path,'')) GLOB '*.pdf' OR lower(COALESCE(f.normalized_path,'')) GLOB '*.docx' OR lower(COALESCE(f.normalized_path,'')) GLOB '*.txt' THEN 'Documents'
      ELSE 'Photos' END"""

    def __init__(self, database: Path) -> None:
        self._factory = SqliteConnectionFactory(database)

    @staticmethod
    def _timestamp_us(value: str, *, end: bool = False) -> int | None:
        if not value:
            return None
        parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if end:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return int(parsed.timestamp() * 1_000_000)

    def filter_options(self, asset_public_ids: tuple[str, ...] | None = None) -> dict[str, tuple[str, ...]]:
        connection = self._factory.connect(read_only=True)
        try:
            restriction, params = self._asset_restriction(asset_public_ids, "a")
            countries = tuple(str(r[0]) for r in connection.execute(
                """SELECT DISTINCT l.country_code FROM assets a
                LEFT JOIN asset_locations al ON al.asset_id=a.id
                LEFT JOIN locations l ON l.id=al.location_id
                WHERE a.lifecycle_state='active' AND l.country_code IS NOT NULL AND trim(l.country_code)<>''"""
                + restriction + " ORDER BY l.country_code", params).fetchall())
            regions = tuple(str(r[0]) for r in connection.execute(
                """SELECT DISTINCT COALESCE(NULLIF(trim(l.admin_area_1),''),NULLIF(trim(l.admin_area_2),''),NULLIF(trim(l.locality),''),NULLIF(trim(l.place_name),'')) region
                FROM assets a LEFT JOIN asset_locations al ON al.asset_id=a.id
                LEFT JOIN locations l ON l.id=al.location_id
                WHERE a.lifecycle_state='active' AND COALESCE(NULLIF(trim(l.admin_area_1),''),NULLIF(trim(l.admin_area_2),''),NULLIF(trim(l.locality),''),NULLIF(trim(l.place_name),'')) IS NOT NULL"""
                + restriction + " ORDER BY region", params).fetchall())
            groups = tuple(str(r[0]) for r in connection.execute(
                """SELECT DISTINCT COALESCE(NULLIF(trim(t.major_group),''),NULLIF(trim(t.kingdom),''),NULLIF(trim(mt.major_group),''),NULLIF(trim(mt.kingdom),''),NULLIF(trim(o.observation_type),''),'Other')
                FROM observations o JOIN assets a ON a.id=o.asset_id
                LEFT JOIN taxa t ON t.id=o.taxon_id LEFT JOIN user_taxa u ON u.id=o.user_taxon_id LEFT JOIN taxa mt ON mt.id=u.mapped_taxon_id
                WHERE a.lifecycle_state='active'""" + restriction + " ORDER BY 1", params).fetchall())
            return {"countries": countries, "regions": regions, "groups": groups}
        finally:
            connection.close()

    @staticmethod
    def _asset_restriction(public_ids: tuple[str, ...] | None, alias: str) -> tuple[str, tuple[object, ...]]:
        if public_ids is None:
            return "", ()
        if not public_ids:
            return " AND 0", ()
        marks = ",".join("?" for _ in public_ids)
        return f" AND {alias}.public_id IN ({marks})", tuple(public_ids)

    def _where(self, filters: AnalyticsFilters, *, include_observation: bool) -> tuple[str, tuple[object, ...]]:
        clauses = ["a.lifecycle_state='active'"]
        params: list[object] = []
        restriction, restriction_params = self._asset_restriction(filters.asset_public_ids, "a")
        if restriction:
            clauses.append(restriction.removeprefix(" AND "))
            params.extend(restriction_params)
        if filters.media_type != "All":
            clauses.append(f"({self.MEDIA_CASE})=?")
            params.append(filters.media_type)
        start = self._timestamp_us(filters.date_from)
        end = self._timestamp_us(filters.date_to, end=True)
        if start is not None:
            clauses.append("a.capture_time_utc_us>=?")
            params.append(start)
        if end is not None:
            clauses.append("a.capture_time_utc_us<=?")
            params.append(end)
        if filters.country != "All":
            clauses.append("COALESCE(l.country_code,'')=?")
            params.append(filters.country)
        if filters.region != "All":
            clauses.append("COALESCE(NULLIF(trim(l.admin_area_1),''),NULLIF(trim(l.admin_area_2),''),NULLIF(trim(l.locality),''),NULLIF(trim(l.place_name),''),'')=?")
            params.append(filters.region)
        if include_observation:
            if filters.taxon_group != "All":
                clauses.append("COALESCE(NULLIF(trim(t.major_group),''),NULLIF(trim(t.kingdom),''),NULLIF(trim(mt.major_group),''),NULLIF(trim(mt.kingdom),''),NULLIF(trim(o.observation_type),''),'Other')=?")
                params.append(filters.taxon_group)
            if filters.review_state != "All":
                clauses.append("COALESCE(o.confirmation_state,'unreviewed')=?")
                params.append(filters.review_state)
        return " AND ".join(clauses), tuple(params)

    def snapshot(self, filters: AnalyticsFilters) -> AnalyticsSnapshot:
        connection = self._factory.connect(read_only=True)
        try:
            joins = """ FROM assets a LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id
            LEFT JOIN asset_locations al ON al.asset_id=a.id AND al.precedence=(SELECT max(al2.precedence) FROM asset_locations al2 WHERE al2.asset_id=a.id)
            LEFT JOIN locations l ON l.id=al.location_id """
            asset_where, asset_params = self._where(filters, include_observation=False)
            obs_joins = joins + " LEFT JOIN observations o ON o.asset_id=a.id LEFT JOIN taxa t ON t.id=o.taxon_id LEFT JOIN user_taxa ut ON ut.id=o.user_taxon_id LEFT JOIN taxa mt ON mt.id=ut.mapped_taxon_id "
            obs_where, obs_params = self._where(filters, include_observation=True)

            asset_count = int(connection.execute("SELECT count(DISTINCT a.id)" + joins + " WHERE " + asset_where, asset_params).fetchone()[0])
            observation_count = int(connection.execute("SELECT count(DISTINCT o.id)" + obs_joins + " WHERE " + obs_where + " AND o.id IS NOT NULL", obs_params).fetchone()[0])
            identified_count = int(connection.execute("SELECT count(DISTINCT o.id)" + obs_joins + " WHERE " + obs_where + " AND o.id IS NOT NULL AND (o.taxon_id IS NOT NULL OR o.user_taxon_id IS NOT NULL)", obs_params).fetchone()[0])
            confirmed_count = int(connection.execute("SELECT count(DISTINCT o.id)" + obs_joins + " WHERE " + obs_where + " AND o.confirmation_state='confirmed'", obs_params).fetchone()[0])

            def pairs(sql: str, params: tuple[object, ...]) -> tuple[tuple[str, int], ...]:
                return tuple((str(r[0] or "Unknown"), int(r[1])) for r in connection.execute(sql, params).fetchall())

            media_assets = pairs("SELECT " + self.MEDIA_CASE + " label,count(DISTINCT a.id)" + joins + " WHERE " + asset_where + " GROUP BY label ORDER BY count(DISTINCT a.id) DESC", asset_params)
            identified_by_media = pairs("SELECT " + self.MEDIA_CASE + " label,count(DISTINCT o.id)" + obs_joins + " WHERE " + obs_where + " AND o.id IS NOT NULL AND (o.taxon_id IS NOT NULL OR o.user_taxon_id IS NOT NULL) GROUP BY label ORDER BY count(DISTINCT o.id) DESC", obs_params)
            observations_by_group = pairs("SELECT COALESCE(NULLIF(trim(t.major_group),''),NULLIF(trim(t.kingdom),''),NULLIF(trim(mt.major_group),''),NULLIF(trim(mt.kingdom),''),NULLIF(trim(o.observation_type),''),'Other') label,count(DISTINCT o.id)" + obs_joins + " WHERE " + obs_where + " AND o.id IS NOT NULL GROUP BY label ORDER BY count(DISTINCT o.id) DESC LIMIT 15", obs_params)
            observations_by_country = pairs("SELECT COALESCE(NULLIF(trim(l.country_code),''),'Unknown') label,count(DISTINCT o.id)" + obs_joins + " WHERE " + obs_where + " AND o.id IS NOT NULL GROUP BY label ORDER BY count(DISTINCT o.id) DESC LIMIT 15", obs_params)
            observations_by_region = pairs("SELECT COALESCE(NULLIF(trim(l.admin_area_1),''),NULLIF(trim(l.admin_area_2),''),NULLIF(trim(l.locality),''),NULLIF(trim(l.place_name),''),'Unknown') label,count(DISTINCT o.id)" + obs_joins + " WHERE " + obs_where + " AND o.id IS NOT NULL GROUP BY label ORDER BY count(DISTINCT o.id) DESC LIMIT 15", obs_params)
            observations_by_month = pairs("SELECT CASE WHEN a.capture_time_utc_us IS NULL THEN 'Unknown' ELSE strftime('%Y-%m',a.capture_time_utc_us/1000000,'unixepoch') END label,count(DISTINCT o.id)" + obs_joins + " WHERE " + obs_where + " AND o.id IS NOT NULL GROUP BY label ORDER BY label", obs_params)
            review_states = pairs("SELECT COALESCE(NULLIF(trim(o.confirmation_state),''),'unreviewed') label,count(DISTINCT o.id)" + obs_joins + " WHERE " + obs_where + " AND o.id IS NOT NULL GROUP BY label ORDER BY count(DISTINCT o.id) DESC", obs_params)
            return AnalyticsSnapshot(asset_count, observation_count, identified_count, confirmed_count, media_assets, identified_by_media, observations_by_group, observations_by_country, observations_by_region, observations_by_month, review_states)
        finally:
            connection.close()
