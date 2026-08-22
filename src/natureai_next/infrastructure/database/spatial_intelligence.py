"""SQLite spatial queries and longitudinal-link operations."""

from __future__ import annotations

from natureai_next.domain.spatial_intelligence import (
    GeoBounds,
    MonitoringSiteSummary,
    SpatialAsset,
    SpatialAssetCluster,
    SpatialObservation,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.unit_of_work import SqliteUnitOfWork


class SqliteSpatialIntelligenceAdapter:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def observations_in_bounds(
        self, bounds: GeoBounds, *, limit: int = 5000
    ) -> tuple[SpatialObservation, ...]:
        c = self._factory.connect(read_only=True)
        try:
            rows = c.execute(
                """SELECT o.id,o.public_id,
                          COALESCE(o.observed_at_us,(SELECT MIN(COALESCE(a.capture_time_utc_us,a.created_at_us)) FROM observation_assets oa JOIN assets a ON a.id=oa.asset_id WHERE oa.observation_id=o.id),o.created_at_us) observed_us,
                          l.latitude,l.longitude,t.scientific_name,
                          (SELECT ms.public_id FROM observation_site_links osl JOIN monitoring_sites ms ON ms.id=osl.site_id WHERE osl.observation_id=o.id ORDER BY ms.id LIMIT 1) site_public_id
                   FROM observations o
                   LEFT JOIN taxa t ON t.id=o.taxon_id
                   JOIN locations l ON l.id=COALESCE(o.location_id,
                       (SELECT al.location_id FROM observation_assets oa JOIN asset_locations al ON al.asset_id=oa.asset_id WHERE oa.observation_id=o.id ORDER BY al.precedence DESC,al.location_id LIMIT 1))
                   WHERE l.latitude BETWEEN ? AND ? AND l.longitude BETWEEN ? AND ?
                   ORDER BY observed_us DESC,o.id DESC LIMIT ?""",
                (
                    bounds.min_latitude,
                    bounds.max_latitude,
                    bounds.min_longitude,
                    bounds.max_longitude,
                    limit,
                ),
            ).fetchall()
            result = []
            for r in rows:
                projects = tuple(
                    str(x[0])
                    for x in c.execute(
                        """SELECT p.public_id FROM observation_project_links op JOIN monitoring_projects p ON p.id=op.project_id WHERE op.observation_id=? ORDER BY p.name COLLATE NOCASE,p.id""",
                        (int(r["id"]),),
                    )
                )
                result.append(
                    SpatialObservation(
                        str(r["public_id"]),
                        int(r["observed_us"]),
                        float(r["latitude"]),
                        float(r["longitude"]),
                        None if r["scientific_name"] is None else str(r["scientific_name"]),
                        None if r["site_public_id"] is None else str(r["site_public_id"]),
                        projects,
                    )
                )
            return tuple(result)
        finally:
            c.close()

    def assets_in_bounds(self, bounds: GeoBounds, *, limit: int = 5000) -> tuple[SpatialAsset, ...]:
        c = self._factory.connect(read_only=True)
        try:
            rows = c.execute(
                """SELECT DISTINCT a.public_id,l.latitude,l.longitude,a.capture_time_utc_us,al.role,a.media_type
                   FROM locations l
                   JOIN asset_locations al ON al.location_id=l.id JOIN assets a ON a.id=al.asset_id
                   WHERE l.latitude BETWEEN ? AND ? AND l.longitude BETWEEN ? AND ?
                     AND a.lifecycle_state='active' 
                   ORDER BY COALESCE(a.capture_time_utc_us,a.created_at_us) DESC,a.id DESC LIMIT ?""",
                (
                    bounds.min_latitude,
                    bounds.max_latitude,
                    bounds.min_longitude,
                    bounds.max_longitude,
                    limit,
                ),
            ).fetchall()
            return tuple(
                SpatialAsset(
                    str(r["public_id"]),
                    float(r["latitude"]),
                    float(r["longitude"]),
                    None if r["capture_time_utc_us"] is None else int(r["capture_time_utc_us"]),
                    str(r["role"]),
                    str(r["media_type"]),
                )
                for r in rows
            )
        finally:
            c.close()


    def asset_clusters_in_bounds(
        self, bounds: GeoBounds, *, zoom: int, limit: int = 5000
    ) -> tuple[SpatialAssetCluster, ...]:
        """Return indexed, zoom-dependent counts for all located media assets."""
        zoom = max(0, min(22, int(zoom)))
        if zoom <= 2:
            level, key_sql, label_sql = "world", "'world'", "'Located media'"
        elif zoom <= 5:
            level = "country"
            key_sql = "COALESCE(NULLIF(l.country_code,''), printf('grid:%d:%d', CAST((l.latitude+90)/30 AS INT), CAST((l.longitude+180)/30 AS INT)))"
            label_sql = "COALESCE(NULLIF(l.country_code,''), 'Geographic area')"
        elif zoom <= 7:
            level = "province"
            key_sql = "COALESCE(NULLIF(l.country_code||':'||l.admin_area_1,':'), printf('grid:%d:%d', CAST((l.latitude+90)/10 AS INT), CAST((l.longitude+180)/10 AS INT)))"
            label_sql = "COALESCE(NULLIF(l.admin_area_1,''), NULLIF(l.country_code,''), 'Regional area')"
        elif zoom <= 10:
            level = "district"
            key_sql = "COALESCE(NULLIF(l.country_code||':'||l.admin_area_1||':'||l.admin_area_2,'::'), NULLIF(l.locality,''), printf('grid:%d:%d', CAST((l.latitude+90)/2 AS INT), CAST((l.longitude+180)/2 AS INT)))"
            label_sql = "COALESCE(NULLIF(l.admin_area_2,''), NULLIF(l.locality,''), NULLIF(l.admin_area_1,''), 'Local area')"
        else:
            # A screen-stable grid narrows from roughly 1 km to exact-place scale.
            decimals = 2 if zoom <= 12 else 3 if zoom <= 15 else 4 if zoom <= 18 else 5
            level = "grid" if decimals < 5 else "location"
            key_sql = f"printf('%.*f:%.*f',{decimals},l.latitude,{decimals},l.longitude)"
            label_sql = "COALESCE(NULLIF(l.place_name,''), NULLIF(l.locality,''), 'Mapped location')"
        c = self._factory.connect(read_only=True)
        try:
            rows = c.execute(
                f"""SELECT AVG(l.latitude) latitude,AVG(l.longitude) longitude,
                           COUNT(DISTINCT a.id) total_count,
                           COUNT(DISTINCT CASE WHEN a.media_type='image' THEN a.id END) image_count,
                           COUNT(DISTINCT CASE WHEN a.media_type='video' THEN a.id END) video_count,
                           COUNT(DISTINCT CASE WHEN a.media_type='audio' THEN a.id END) audio_count,
                           COUNT(DISTINCT CASE WHEN al.role='capture' THEN a.id END) capture_count,
                           COUNT(DISTINCT CASE WHEN al.role='subject' THEN a.id END) subject_count,
                           COUNT(DISTINCT CASE WHEN al.role='user_defined' THEN a.id END) user_defined_count,
                           {label_sql} label
                    FROM locations l
                    JOIN asset_locations al ON al.location_id=l.id
                    JOIN assets a ON a.id=al.asset_id
                    WHERE l.latitude BETWEEN ? AND ? AND l.longitude BETWEEN ? AND ?
                      AND a.lifecycle_state='active'
                    GROUP BY {key_sql}
                    ORDER BY total_count DESC LIMIT ?""",
                (bounds.min_latitude,bounds.max_latitude,bounds.min_longitude,bounds.max_longitude,limit),
            ).fetchall()
            return tuple(SpatialAssetCluster(
                float(r['latitude']), float(r['longitude']), int(r['total_count']),
                int(r['image_count']), int(r['video_count']), int(r['audio_count']),
                int(r['capture_count']), int(r['subject_count']), int(r['user_defined_count']),
                level, str(r['label'])
            ) for r in rows)
        finally:
            c.close()

    def list_sites_in_bounds(
        self, bounds: GeoBounds, *, limit: int = 1000
    ) -> tuple[MonitoringSiteSummary, ...]:
        c = self._factory.connect(read_only=True)
        try:
            rows = c.execute(
                """SELECT s.public_id,s.name,l.latitude,l.longitude,s.status FROM monitoring_sites s JOIN locations l ON l.id=s.location_id
                   WHERE l.latitude BETWEEN ? AND ? AND l.longitude BETWEEN ? AND ? ORDER BY s.name COLLATE NOCASE,s.id LIMIT ?""",
                (
                    bounds.min_latitude,
                    bounds.max_latitude,
                    bounds.min_longitude,
                    bounds.max_longitude,
                    limit,
                ),
            ).fetchall()
            return tuple(
                MonitoringSiteSummary(
                    str(r["public_id"]),
                    str(r["name"]),
                    float(r["latitude"]),
                    float(r["longitude"]),
                    str(r["status"]),
                )
                for r in rows
            )
        finally:
            c.close()

    def link_observation_to_project(
        self, observation_public_id: str, project_public_id: str, *, now_us: int
    ) -> None:
        self._link(
            "observation_project_links",
            "project_id",
            "monitoring_projects",
            observation_public_id,
            project_public_id,
            now_us,
        )

    def link_observation_to_site(
        self, observation_public_id: str, site_public_id: str, *, now_us: int
    ) -> None:
        self._link(
            "observation_site_links",
            "site_id",
            "monitoring_sites",
            observation_public_id,
            site_public_id,
            now_us,
        )

    def _link(
        self,
        table: str,
        target_column: str,
        target_table: str,
        observation_public_id: str,
        target_public_id: str,
        now_us: int,
    ) -> None:
        with SqliteUnitOfWork(self._factory) as u:
            c = u.connection
            assert c is not None
            o = c.execute(
                "SELECT id FROM observations WHERE public_id=?", (observation_public_id,)
            ).fetchone()
            target = c.execute(
                f"SELECT id FROM {target_table} WHERE public_id=?", (target_public_id,)
            ).fetchone()
            if o is None:
                raise KeyError(observation_public_id)
            if target is None:
                raise KeyError(target_public_id)
            c.execute(
                f"INSERT OR IGNORE INTO {table}(observation_id,{target_column},linked_at_us) VALUES(?,?,?)",
                (int(o[0]), int(target[0]), now_us),
            )
            u.commit()

    def observations_in_time_window(
        self,
        bounds: GeoBounds,
        *,
        start_us: int,
        end_us: int,
        cumulative: bool = False,
        limit: int = 5000,
    ):
        """Return map-ready observations for a temporal frame.

        Snapshot mode selects start <= observed <= end. Cumulative mode selects
        all records observed up to end while retaining the lower bound only as a
        playback origin for the caller.
        """
        from natureai_next.domain.temporal_movement import TemporalObservationPoint

        if end_us < start_us:
            raise ValueError("time window end precedes start")
        c = self._factory.connect(read_only=True)
        try:
            time_predicate = "observed_us <= ?" if cumulative else "observed_us BETWEEN ? AND ?"
            params = [
                bounds.min_latitude,
                bounds.max_latitude,
                bounds.min_longitude,
                bounds.max_longitude,
            ]
            params.extend([end_us] if cumulative else [start_us, end_us])
            params.append(limit)
            rows = c.execute(
                f"""WITH temporal AS (
                       SELECT o.id,o.public_id,
                              COALESCE(o.observed_at_us,
                                (SELECT MIN(COALESCE(a.capture_time_utc_us,a.created_at_us))
                                 FROM observation_assets oa JOIN assets a ON a.id=oa.asset_id
                                 WHERE oa.observation_id=o.id),o.created_at_us) AS observed_us,
                              l.latitude,l.longitude,t.scientific_name
                       FROM observations o
                       LEFT JOIN taxa t ON t.id=o.taxon_id
                       JOIN locations l ON l.id=COALESCE(o.location_id,
                         (SELECT al.location_id FROM observation_assets oa
                          JOIN asset_locations al ON al.asset_id=oa.asset_id
                          WHERE oa.observation_id=o.id
                          ORDER BY al.precedence DESC,al.location_id LIMIT 1))
                       WHERE l.latitude BETWEEN ? AND ? AND l.longitude BETWEEN ? AND ?
                   )
                   SELECT temporal.*,
                          s.public_id AS series_public_id,
                          COALESCE(sm.identity_confidence,s.identity_confidence,'unknown') AS identity_confidence,
                          COALESCE(s.connection_policy,'observed_locations') AS connection_policy
                   FROM temporal
                   LEFT JOIN observation_series_members sm ON sm.observation_id=temporal.id
                   LEFT JOIN observation_series s ON s.id=sm.series_id
                   WHERE {time_predicate}
                   ORDER BY observed_us,temporal.id
                   LIMIT ?""",
                tuple(params),
            ).fetchall()
            return tuple(
                TemporalObservationPoint(
                    observation_public_id=str(r["public_id"]),
                    observed_at_us=int(r["observed_us"]),
                    latitude=float(r["latitude"]),
                    longitude=float(r["longitude"]),
                    scientific_name=None
                    if r["scientific_name"] is None
                    else str(r["scientific_name"]),
                    series_public_id=None
                    if r["series_public_id"] is None
                    else str(r["series_public_id"]),
                    identity_confidence=str(r["identity_confidence"]),
                    connection_policy=str(r["connection_policy"]),
                )
                for r in rows
            )
        finally:
            c.close()

    def movement_track(
        self, series_public_id: str, *, start_us: int | None = None, end_us: int | None = None
    ):
        """Return an ordered series track, preserving its evidence qualification."""
        from natureai_next.domain.temporal_movement import (
            MovementEvidenceMode,
            MovementTrack,
            MovementTrackPoint,
        )

        if start_us is not None and end_us is not None and end_us < start_us:
            raise ValueError("time window end precedes start")
        c = self._factory.connect(read_only=True)
        try:
            series = c.execute(
                """SELECT id,public_id,title,subject_type,subject_identifier,identity_confidence,
                          tracking_method,connection_policy
                   FROM observation_series WHERE public_id=?""",
                (series_public_id,),
            ).fetchone()
            if series is None:
                raise KeyError(series_public_id)
            clauses = []
            params: list[object] = [int(series["id"])]
            if start_us is not None:
                clauses.append("observed_us>=?")
                params.append(start_us)
            if end_us is not None:
                clauses.append("observed_us<=?")
                params.append(end_us)
            where_time = " AND " + " AND ".join(clauses) if clauses else ""
            rows = c.execute(
                f"""WITH members AS (
                       SELECT sm.observation_id,sm.sequence_number,sm.identity_confidence,sm.verified,
                              COALESCE(sm.tracking_timestamp_us,o.observed_at_us,
                                (SELECT MIN(COALESCE(a.capture_time_utc_us,a.created_at_us))
                                 FROM observation_assets oa JOIN assets a ON a.id=oa.asset_id
                                 WHERE oa.observation_id=o.id),o.created_at_us) AS observed_us,
                              o.public_id,
                              l.latitude,l.longitude
                       FROM observation_series_members sm
                       JOIN observations o ON o.id=sm.observation_id
                       JOIN locations l ON l.id=COALESCE(o.location_id,
                         (SELECT al.location_id FROM observation_assets oa
                          JOIN asset_locations al ON al.asset_id=oa.asset_id
                          WHERE oa.observation_id=o.id
                          ORDER BY al.precedence DESC,al.location_id LIMIT 1))
                       WHERE sm.series_id=?
                   )
                   SELECT * FROM members WHERE 1=1 {where_time}
                   ORDER BY COALESCE(sequence_number,2147483647),observed_us,observation_id""",
                tuple(params),
            ).fetchall()
            points = tuple(
                MovementTrackPoint(
                    observation_public_id=str(r["public_id"]),
                    observed_at_us=int(r["observed_us"]),
                    latitude=float(r["latitude"]),
                    longitude=float(r["longitude"]),
                    sequence_number=None
                    if r["sequence_number"] is None
                    else int(r["sequence_number"]),
                    identity_confidence=str(r["identity_confidence"]),
                    verified=bool(r["verified"]),
                )
                for r in rows
            )
            return MovementTrack(
                series_public_id=str(series["public_id"]),
                title=str(series["title"]),
                subject_type=str(series["subject_type"]),
                subject_identifier=None
                if series["subject_identifier"] is None
                else str(series["subject_identifier"]),
                identity_confidence=str(series["identity_confidence"]),
                tracking_method=str(series["tracking_method"]),
                evidence_mode=MovementEvidenceMode(str(series["connection_policy"])),
                points=points,
            )
        finally:
            c.close()
