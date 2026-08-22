"""SQLite observation-history queries, species history, and evidence linking."""

from __future__ import annotations

from natureai_next.domain.observation_intelligence import (
    LifeListEntry,
    ObservationEvidencePhoto,
    ObservationInspectorRecord,
    ObservationStatistics,
    ObservationTimelineEntry,
    PersonalObservationContext,
    SpeciesObservationHistory,
    SpeciesObservationSummary,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.unit_of_work import SqliteUnitOfWork


class SqliteObservationIntelligenceAdapter:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    @staticmethod
    def _observed_time_sql(alias: str = "o") -> str:
        return f"COALESCE({alias}.observed_at_us, (SELECT MIN(COALESCE(a.capture_time_utc_us, a.created_at_us)) FROM observation_assets ox JOIN assets a ON a.id=ox.asset_id WHERE ox.observation_id={alias}.id), {alias}.created_at_us)"

    def _taxon_id(self, connection: object, taxon_public_id: str) -> int:
        row = connection.execute(
            "SELECT id FROM taxa WHERE public_id=?", (taxon_public_id,)
        ).fetchone()
        if row is None:
            raise KeyError(taxon_public_id)
        return int(row[0])

    def context_for_taxon(self, taxon_public_id: str) -> PersonalObservationContext:
        c = self._factory.connect(read_only=True)
        try:
            taxon_id = self._taxon_id(c, taxon_public_id)
            observed = self._observed_time_sql("o")
            row = c.execute(
                f"""SELECT COUNT(DISTINCT o.id) observation_count,
                           MIN({observed}) first_us, MAX({observed}) last_us,
                           COUNT(DISTINCT oa.asset_id) photo_count
                    FROM observations o
                    LEFT JOIN observation_assets oa ON oa.observation_id=o.id
                    WHERE o.taxon_id=? AND o.confirmation_state='confirmed'""",
                (taxon_id,),
            ).fetchone()
            countries = tuple(
                str(r[0])
                for r in c.execute(
                    """SELECT DISTINCT l.country_code FROM observations o
                   JOIN observation_assets oa ON oa.observation_id=o.id
                   JOIN asset_locations al ON al.asset_id=oa.asset_id
                   JOIN locations l ON l.id=al.location_id
                   WHERE o.taxon_id=? AND o.confirmation_state='confirmed'
                     AND l.country_code IS NOT NULL AND trim(l.country_code)<>''
                   ORDER BY l.country_code""",
                    (taxon_id,),
                )
            )
            return PersonalObservationContext(
                taxon_public_id=taxon_public_id,
                confirmed_observations=int(row["observation_count"] or 0),
                evidence_photos=int(row["photo_count"] or 0),
                first_observed_at_us=None if row["first_us"] is None else int(row["first_us"]),
                last_observed_at_us=None if row["last_us"] is None else int(row["last_us"]),
                country_codes=countries,
            )
        finally:
            c.close()

    def list_species(self, *, limit: int = 500) -> tuple[SpeciesObservationSummary, ...]:
        c = self._factory.connect(read_only=True)
        try:
            observed = self._observed_time_sql("o")
            rows = c.execute(
                f"""SELECT t.id taxon_id,t.public_id,t.scientific_name,t.rank,
                           COUNT(DISTINCT o.id) observation_count,
                           COUNT(DISTINCT oa.asset_id) photo_count,
                           MIN({observed}) first_us,MAX({observed}) last_us
                    FROM taxa t JOIN observations o ON o.taxon_id=t.id
                    LEFT JOIN observation_assets oa ON oa.observation_id=o.id
                    WHERE o.confirmation_state='confirmed'
                    GROUP BY t.id,t.public_id,t.scientific_name,t.rank
                    ORDER BY t.scientific_name COLLATE NOCASE LIMIT ?""",
                (limit,),
            ).fetchall()
            result = []
            for row in rows:
                countries = tuple(
                    str(r[0])
                    for r in c.execute(
                        """SELECT DISTINCT l.country_code FROM observations o
                       JOIN observation_assets oa ON oa.observation_id=o.id
                       JOIN asset_locations al ON al.asset_id=oa.asset_id
                       JOIN locations l ON l.id=al.location_id
                       WHERE o.taxon_id=? AND o.confirmation_state='confirmed'
                         AND l.country_code IS NOT NULL AND trim(l.country_code)<>''
                       ORDER BY l.country_code""",
                        (int(row["taxon_id"]),),
                    )
                )
                result.append(
                    SpeciesObservationSummary(
                        taxon_public_id=str(row["public_id"]),
                        scientific_name=str(row["scientific_name"]),
                        rank=None if row["rank"] is None else str(row["rank"]),
                        observation_count=int(row["observation_count"]),
                        evidence_photo_count=int(row["photo_count"]),
                        first_observed_at_us=None
                        if row["first_us"] is None
                        else int(row["first_us"]),
                        last_observed_at_us=None if row["last_us"] is None else int(row["last_us"]),
                        country_codes=countries,
                    )
                )
            return tuple(result)
        finally:
            c.close()

    def history_for_taxon(self, taxon_public_id: str) -> SpeciesObservationHistory:
        c = self._factory.connect(read_only=True)
        try:
            taxon_id = self._taxon_id(c, taxon_public_id)
            summaries = {item.taxon_public_id: item for item in self.list_species(limit=5000)}
            summary = summaries.get(taxon_public_id)
            if summary is None:
                taxon = c.execute(
                    "SELECT scientific_name,rank FROM taxa WHERE id=?", (taxon_id,)
                ).fetchone()
                summary = SpeciesObservationSummary(
                    taxon_public_id, str(taxon[0]), taxon[1], 0, 0, None, None, ()
                )
            observed = self._observed_time_sql("o")
            observations = c.execute(
                f"""SELECT o.id,o.public_id,o.notes,{observed} observed_us
                    FROM observations o WHERE o.taxon_id=? AND o.confirmation_state='confirmed'
                    ORDER BY observed_us DESC,o.id DESC""",
                (taxon_id,),
            ).fetchall()
            timeline = []
            for obs in observations:
                photos = []
                photo_rows = c.execute(
                    """SELECT a.id,a.public_id,a.capture_time_utc_us,a.capture_local_text,f.normalized_path,oa.role,
                              (SELECT d.relative_path FROM derivative_cache_entries d
                               WHERE d.source_file_instance_id=f.id AND d.derivative_kind='thumbnail' AND d.state='valid'
                               ORDER BY d.created_at_us DESC LIMIT 1) thumbnail_path,
                              (SELECT l.country_code FROM asset_locations al JOIN locations l ON l.id=al.location_id
                               WHERE al.asset_id=a.id ORDER BY al.precedence DESC LIMIT 1) country_code
                       FROM observation_assets oa JOIN assets a ON a.id=oa.asset_id
                       LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id
                       WHERE oa.observation_id=?
                       ORDER BY CASE oa.role WHEN 'primary' THEN 0 ELSE 1 END,oa.linked_at_us,a.id""",
                    (int(obs["id"]),),
                ).fetchall()
                for photo in photo_rows:
                    collections = tuple(
                        str(r[0])
                        for r in c.execute(
                            """SELECT co.name FROM collections co JOIN collection_assets ca ON ca.collection_id=co.id
                           WHERE ca.asset_id=? ORDER BY co.name COLLATE NOCASE""",
                            (int(photo["id"]),),
                        )
                    )
                    photos.append(
                        ObservationEvidencePhoto(
                            asset_public_id=str(photo["public_id"]),
                            primary_path=None
                            if photo["normalized_path"] is None
                            else str(photo["normalized_path"]),
                            thumbnail_path=None
                            if photo["thumbnail_path"] is None
                            else str(photo["thumbnail_path"]),
                            captured_at_us=None
                            if photo["capture_time_utc_us"] is None
                            else int(photo["capture_time_utc_us"]),
                            capture_local_text=None
                            if photo["capture_local_text"] is None
                            else str(photo["capture_local_text"]),
                            country_code=None
                            if photo["country_code"] is None
                            else str(photo["country_code"]),
                            collection_names=collections,
                            role=str(photo["role"]),
                        )
                    )
                explicit_country = c.execute(
                    "SELECT l.country_code FROM observations o LEFT JOIN locations l ON l.id=o.location_id WHERE o.id=?",
                    (int(obs["id"]),),
                ).fetchone()
                country = (None if explicit_country is None else explicit_country[0]) or next(
                    (p.country_code for p in photos if p.country_code), None
                )
                timeline.append(
                    ObservationTimelineEntry(
                        observation_public_id=str(obs["public_id"]),
                        observed_at_us=int(obs["observed_us"]),
                        country_code=country,
                        notes=None if obs["notes"] is None else str(obs["notes"]),
                        photos=tuple(photos),
                    )
                )
            return SpeciesObservationHistory(summary=summary, timeline=tuple(timeline))
        finally:
            c.close()

    def related_taxa(
        self, taxon_public_id: str, *, limit: int = 8
    ) -> tuple[tuple[str, str, str | None], ...]:
        c = self._factory.connect(read_only=True)
        try:
            row = c.execute(
                "SELECT id,parent_taxon_id,kingdom,major_group FROM taxa WHERE public_id=?",
                (taxon_public_id,),
            ).fetchone()
            if row is None:
                raise KeyError(taxon_public_id)
            parent_id = row["parent_taxon_id"]
            if parent_id is not None:
                rows = c.execute(
                    """SELECT DISTINCT t.public_id,t.scientific_name,t.rank FROM taxa t JOIN observations o ON o.taxon_id=t.id AND o.confirmation_state='confirmed'
                                    WHERE t.parent_taxon_id=? AND t.public_id<>? AND t.status='accepted'
                                    ORDER BY scientific_name COLLATE NOCASE LIMIT ?""",
                    (int(parent_id), taxon_public_id, limit),
                ).fetchall()
            else:
                rows = c.execute(
                    """SELECT DISTINCT t.public_id,t.scientific_name,t.rank FROM taxa t JOIN observations o ON o.taxon_id=t.id AND o.confirmation_state='confirmed'
                                    WHERE t.public_id<>? AND t.status='accepted'
                                      AND COALESCE(t.major_group,'')=COALESCE(?, '')
                                      AND COALESCE(t.kingdom,'')=COALESCE(?, '')
                                    ORDER BY scientific_name COLLATE NOCASE LIMIT ?""",
                    (taxon_public_id, row["major_group"], row["kingdom"], limit),
                ).fetchall()
            return tuple(
                (
                    str(r["public_id"]),
                    str(r["scientific_name"]),
                    None if r["rank"] is None else str(r["rank"]),
                )
                for r in rows
            )
        finally:
            c.close()

    def statistics(self, *, current_year: int) -> ObservationStatistics:
        c = self._factory.connect(read_only=True)
        try:
            observed = self._observed_time_sql("o")
            totals = c.execute(
                """SELECT COUNT(DISTINCT o.taxon_id) species_count,
                           COUNT(DISTINCT o.id) observation_count,
                           COUNT(DISTINCT oa.asset_id) photo_count
                    FROM observations o LEFT JOIN observation_assets oa ON oa.observation_id=o.id
                    WHERE o.confirmation_state='confirmed'"""
            ).fetchone()
            country_count = int(
                c.execute(
                    """SELECT COUNT(DISTINCT l.country_code) FROM observations o
                   JOIN observation_assets oa ON oa.observation_id=o.id
                   JOIN asset_locations al ON al.asset_id=oa.asset_id
                   JOIN locations l ON l.id=al.location_id
                   WHERE o.confirmation_state='confirmed' AND l.country_code IS NOT NULL
                     AND trim(l.country_code)<>''"""
                ).fetchone()[0]
            )
            year_start = int(
                __import__("datetime")
                .datetime(current_year, 1, 1, tzinfo=__import__("datetime").timezone.utc)
                .timestamp()
                * 1_000_000
            )
            year_end = int(
                __import__("datetime")
                .datetime(current_year + 1, 1, 1, tzinfo=__import__("datetime").timezone.utc)
                .timestamp()
                * 1_000_000
            )
            first_this_year = int(
                c.execute(
                    f"""SELECT COUNT(*) FROM (
                    SELECT o.taxon_id, MIN({observed}) first_us FROM observations o
                    WHERE o.confirmation_state='confirmed' GROUP BY o.taxon_id
                ) WHERE first_us>=? AND first_us<?""",
                    (year_start, year_end),
                ).fetchone()[0]
            )
            group_rows = c.execute(
                """SELECT COALESCE(NULLIF(trim(t.major_group),''), NULLIF(trim(t.kingdom),''), 'Other') group_name,
                          COUNT(DISTINCT t.id) species_count, COUNT(DISTINCT o.id) observation_count,
                          COUNT(DISTINCT oa.asset_id) photo_count
                   FROM taxa t JOIN observations o ON o.taxon_id=t.id
                   LEFT JOIN observation_assets oa ON oa.observation_id=o.id
                   WHERE o.confirmation_state='confirmed'
                   GROUP BY group_name ORDER BY species_count DESC, group_name COLLATE NOCASE"""
            ).fetchall()
            life = tuple(
                LifeListEntry(
                    str(r["group_name"]),
                    int(r["species_count"]),
                    int(r["observation_count"]),
                    int(r["photo_count"]),
                )
                for r in group_rows
            )
            species = sorted(
                self.list_species(limit=5000),
                key=lambda x: (-x.observation_count, x.scientific_name.casefold()),
            )[:10]
            return ObservationStatistics(
                species_count=int(totals["species_count"] or 0),
                observation_count=int(totals["observation_count"] or 0),
                evidence_photo_count=int(totals["photo_count"] or 0),
                country_count=country_count,
                first_observations_this_year=first_this_year,
                most_observed_species=tuple(species),
                life_list=life,
            )
        finally:
            c.close()

    def link_asset(self, observation_public_id: str, asset_public_id: str, *, now_us: int) -> None:
        with SqliteUnitOfWork(self._factory) as u:
            c = u.connection
            assert c is not None
            observation = c.execute(
                "SELECT id FROM observations WHERE public_id=?", (observation_public_id,)
            ).fetchone()
            asset = c.execute(
                "SELECT id FROM assets WHERE public_id=?", (asset_public_id,)
            ).fetchone()
            if observation is None:
                raise KeyError(observation_public_id)
            if asset is None:
                raise KeyError(asset_public_id)
            c.execute(
                "INSERT OR IGNORE INTO observation_assets(observation_id,asset_id,role,linked_at_us) VALUES(?,?,'evidence',?)",
                (int(observation[0]), int(asset[0]), now_us),
            )
            u.commit()

    def set_context(
        self,
        observation_public_id: str,
        *,
        observed_at_us: int | None,
        latitude: float | None,
        longitude: float | None,
        altitude_m: float | None,
        accuracy_m: float | None,
        now_us: int,
        source: str = "user",
    ) -> None:
        if source not in {"user", "import", "plugin", "asset_metadata"}:
            raise ValueError("invalid observation context source")
        if (latitude is None) != (longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        if latitude is not None and not -90 <= latitude <= 90:
            raise ValueError("latitude is invalid")
        if longitude is not None and not -180 <= longitude <= 180:
            raise ValueError("longitude is invalid")
        if accuracy_m is not None and accuracy_m < 0:
            raise ValueError("accuracy is invalid")
        with SqliteUnitOfWork(self._factory) as u:
            c = u.connection
            assert c is not None
            row = c.execute(
                "SELECT id FROM observations WHERE public_id=?", (observation_public_id,)
            ).fetchone()
            if row is None:
                raise KeyError(observation_public_id)
            location_id = None
            if latitude is not None and longitude is not None:
                import uuid

                location_id = c.execute(
                    "INSERT INTO locations(public_id,latitude,longitude,altitude_m,accuracy_m,source,confidence,created_at_us) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()),
                        latitude,
                        longitude,
                        altitude_m,
                        accuracy_m,
                        source,
                        1.0,
                        now_us,
                    ),
                ).lastrowid
            c.execute(
                "UPDATE observations SET observed_at_us=?,location_id=?,time_source=?,location_source=?,location_accuracy_m=?,modified_at_us=?,revision=revision+1 WHERE id=?",
                (
                    observed_at_us,
                    location_id,
                    source if observed_at_us is not None else "derived",
                    source if location_id is not None else "derived",
                    accuracy_m,
                    now_us,
                    int(row[0]),
                ),
            )
            u.commit()

    def inspect(self, observation_public_id: str) -> ObservationInspectorRecord:
        c = self._factory.connect(read_only=True)
        try:
            row = c.execute(
                """SELECT o.id,o.public_id,t.public_id taxon_public_id,t.scientific_name,o.confirmation_state,
                          o.created_at_us,o.modified_at_us,o.revision
                   FROM observations o LEFT JOIN taxa t ON t.id=o.taxon_id WHERE o.public_id=?""",
                (observation_public_id,),
            ).fetchone()
            if row is None:
                raise KeyError(observation_public_id)
            assets = tuple(
                str(r[0])
                for r in c.execute(
                    """SELECT a.public_id FROM observation_assets oa JOIN assets a ON a.id=oa.asset_id
                   WHERE oa.observation_id=? ORDER BY CASE oa.role WHEN 'primary' THEN 0 ELSE 1 END,oa.linked_at_us,a.id""",
                    (int(row["id"]),),
                )
            )
            return ObservationInspectorRecord(
                public_id=str(row["public_id"]),
                taxon_public_id=None
                if row["taxon_public_id"] is None
                else str(row["taxon_public_id"]),
                scientific_name=None
                if row["scientific_name"] is None
                else str(row["scientific_name"]),
                confirmation_state=str(row["confirmation_state"]),
                created_at_us=int(row["created_at_us"]),
                modified_at_us=int(row["modified_at_us"]),
                revision=int(row["revision"]),
                asset_public_ids=assets,
            )
        finally:
            c.close()
