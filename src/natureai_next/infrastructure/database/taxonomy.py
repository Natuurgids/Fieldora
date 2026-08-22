"""SQLite taxonomy, observation, ROI, and user-taxon adapters."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict

from natureai_next.domain.taxonomy import (
    ObservationDraft,
    ObservationView,
    RegionOfInterestDraft,
    TaxonomyPackageData,
    TaxonPage,
    TaxonSummary,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.unit_of_work import SqliteUnitOfWork


def _public_taxon_id(source_name: str, source_taxon_id: str) -> str:
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"natureai-next:taxonomy:{source_name}:{source_taxon_id}")
    )


def _validate_graph(package: TaxonomyPackageData) -> None:
    by_id = {x.source_taxon_id: x for x in package.taxa}
    if len(by_id) != len(package.taxa):
        raise ValueError("duplicate source taxon identifier")
    for item in package.taxa:
        if item.parent_source_taxon_id and item.parent_source_taxon_id not in by_id:
            raise ValueError(f"missing parent taxon: {item.parent_source_taxon_id}")
        if item.accepted_source_taxon_id and item.accepted_source_taxon_id not in by_id:
            raise ValueError(f"missing accepted taxon: {item.accepted_source_taxon_id}")
        if (
            item.accepted_source_taxon_id
            and by_id[item.accepted_source_taxon_id].status.value != "accepted"
        ):
            raise ValueError("synonym target must be accepted")
    state: dict[str, int] = {}

    def visit(identifier: str) -> None:
        value = state.get(identifier, 0)
        if value == 1:
            raise ValueError("taxonomy hierarchy contains a cycle")
        if value == 2:
            return
        state[identifier] = 1
        parent = by_id[identifier].parent_source_taxon_id
        if parent:
            visit(parent)
        state[identifier] = 2

    for identifier in by_id:
        visit(identifier)


class SqliteTaxonomyAdapter:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def install(self, package: TaxonomyPackageData, *, now_us: int) -> str:
        """Stage, validate, and atomically publish a taxonomy package.

        Stable taxon public IDs are updated in place so repeated regional installs
        cannot fail on ``taxa.public_id``.  The active taxonomy remains untouched
        while raw/normalized rows are staged, and becomes visible only at publish.
        """
        _validate_graph(package)
        token = str(uuid.uuid4())
        taxon_ids = {
            x.source_taxon_id: _public_taxon_id(package.source_name, x.source_taxon_id)
            for x in package.taxa
        }
        license_json = json.dumps(asdict(package.license), sort_keys=True, separators=(",", ":"))
        manifest_json = json.dumps(
            {"package_id": package.package_id, "minimum_app_version": package.minimum_app_version},
            sort_keys=True,
            separators=(",", ":"),
        )

        # Staging is deliberately persistent rather than TEMP: each dependency
        # phase can commit independently and an interrupted conversion can be
        # diagnosed or cleaned without exposing partial master data.
        c = self._factory.connect()
        try:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS taxonomy_stage_taxa(
              token TEXT NOT NULL, source_taxon_id TEXT NOT NULL, public_id TEXT NOT NULL,
              scientific_name TEXT NOT NULL, authorship TEXT, rank TEXT NOT NULL,
              status TEXT NOT NULL, kingdom TEXT, major_group TEXT, extinct INTEGER NOT NULL,
              parent_source_taxon_id TEXT, accepted_source_taxon_id TEXT,
              PRIMARY KEY(token,source_taxon_id));
            CREATE TABLE IF NOT EXISTS taxonomy_stage_names(
              token TEXT NOT NULL, source_taxon_id TEXT NOT NULL, language_tag TEXT,
              region_code TEXT, name TEXT NOT NULL, name_type TEXT NOT NULL,
              preferred INTEGER NOT NULL, source TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS taxonomy_stage_regions(
              token TEXT NOT NULL, source_taxon_id TEXT NOT NULL, region_code TEXT NOT NULL,
              occurrence_status TEXT, source TEXT NOT NULL);
            """)
            rank_phases = (
                ("family", {"kingdom", "phylum", "class", "order", "family"}),
                ("genus", {"genus", "subgenus"}),
                ("species", None),
            )
            staged: set[str] = set()
            for _phase, ranks in rank_phases:
                rows = []
                for item in package.taxa:
                    if item.source_taxon_id in staged:
                        continue
                    if ranks is not None and item.rank.casefold() not in ranks:
                        continue
                    rows.append(
                        (
                            token,
                            item.source_taxon_id,
                            taxon_ids[item.source_taxon_id],
                            item.scientific_name,
                            item.authorship,
                            item.rank,
                            item.status.value,
                            item.kingdom,
                            item.major_group,
                            int(item.extinct),
                            item.parent_source_taxon_id,
                            item.accepted_source_taxon_id,
                        )
                    )
                    staged.add(item.source_taxon_id)
                if rows:
                    c.execute("BEGIN IMMEDIATE")
                    c.executemany(
                        "INSERT INTO taxonomy_stage_taxa VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", rows
                    )
                    c.execute("COMMIT")
            c.execute("BEGIN IMMEDIATE")
            c.executemany(
                "INSERT INTO taxonomy_stage_names VALUES(?,?,?,?,?,?,?,?)",
                [
                    (
                        token,
                        x.source_taxon_id,
                        x.language_tag,
                        x.region_code.upper() if x.region_code else None,
                        x.name,
                        x.name_type,
                        int(x.preferred),
                        x.source,
                    )
                    for x in package.names
                ],
            )
            c.executemany(
                "INSERT INTO taxonomy_stage_regions VALUES(?,?,?,?,?)",
                [
                    (token, x.source_taxon_id, x.region_code, x.occurrence_status, x.source)
                    for x in package.regions
                ],
            )
            c.execute("COMMIT")

            count = int(
                c.execute(
                    "SELECT count(*) FROM taxonomy_stage_taxa WHERE token=?", (token,)
                ).fetchone()[0]
            )
            if count != len(package.taxa):
                raise ValueError("staged taxonomy row count does not match verified package")
            unknown_names = int(
                c.execute(
                    "SELECT count(*) FROM taxonomy_stage_names n LEFT JOIN taxonomy_stage_taxa t ON t.token=n.token AND t.source_taxon_id=n.source_taxon_id WHERE n.token=? AND t.source_taxon_id IS NULL",
                    (token,),
                ).fetchone()[0]
            )
            unknown_regions = int(
                c.execute(
                    "SELECT count(*) FROM taxonomy_stage_regions r LEFT JOIN taxonomy_stage_taxa t ON t.token=r.token AND t.source_taxon_id=r.source_taxon_id WHERE r.token=? AND t.source_taxon_id IS NULL",
                    (token,),
                ).fetchone()[0]
            )
            if unknown_names or unknown_regions:
                raise ValueError("staged taxonomy contains references to unknown taxa")

            c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT public_id,package_checksum FROM taxonomy_sources WHERE package_id=?",
                (package.package_id,),
            ).fetchone()
            if existing:
                if existing["package_checksum"] != package.checksum:
                    raise ValueError("installed taxonomy package identity has a different checksum")
                c.execute("ROLLBACK")
                return str(existing["public_id"])
            source_public_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"natureai-next:taxonomy-source:{package.source_name}:{package.source_version}",
                )
            )
            c.execute(
                "INSERT INTO taxonomy_sources(public_id,name,source_version,package_checksum,license_json,installed_at_us,activated_at_us,active,package_id,attribution_text,manifest_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    source_public_id,
                    package.source_name,
                    package.source_version,
                    package.checksum,
                    license_json,
                    now_us,
                    None,
                    0,
                    package.package_id,
                    package.attribution_text,
                    manifest_json,
                ),
            )
            source_id = int(c.execute("SELECT last_insert_rowid()").fetchone()[0])
            stage_rows = c.execute(
                "SELECT * FROM taxonomy_stage_taxa WHERE token=?", (token,)
            ).fetchall()
            db_ids = {}
            for item in stage_rows:
                old = c.execute(
                    "SELECT id FROM taxa WHERE public_id=?", (item["public_id"],)
                ).fetchone()
                values = (
                    source_id,
                    item["source_taxon_id"],
                    item["scientific_name"],
                    item["authorship"],
                    item["rank"],
                    item["status"],
                    item["kingdom"],
                    item["major_group"],
                    item["extinct"],
                )
                if old:
                    taxon_id = int(old["id"])
                    c.execute(
                        "UPDATE taxa SET source_id=?,source_taxon_id=?,scientific_name=?,authorship=?,rank=?,status=?,kingdom=?,major_group=?,extinct=?,parent_taxon_id=NULL,accepted_taxon_id=NULL WHERE id=?",
                        (*values, taxon_id),
                    )
                    c.execute("DELETE FROM taxon_names WHERE taxon_id=?", (taxon_id,))
                    c.execute("DELETE FROM taxon_regions WHERE taxon_id=?", (taxon_id,))
                else:
                    c.execute(
                        "INSERT INTO taxa(source_id,source_taxon_id,public_id,scientific_name,authorship,rank,status,kingdom,major_group,extinct) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            source_id,
                            item["source_taxon_id"],
                            item["public_id"],
                            item["scientific_name"],
                            item["authorship"],
                            item["rank"],
                            item["status"],
                            item["kingdom"],
                            item["major_group"],
                            item["extinct"],
                        ),
                    )
                    taxon_id = int(c.execute("SELECT last_insert_rowid()").fetchone()[0])
                db_ids[str(item["source_taxon_id"])] = taxon_id
            for item in stage_rows:
                c.execute(
                    "UPDATE taxa SET parent_taxon_id=?,accepted_taxon_id=? WHERE id=?",
                    (
                        db_ids.get(item["parent_source_taxon_id"]),
                        db_ids.get(item["accepted_source_taxon_id"]),
                        db_ids[str(item["source_taxon_id"])],
                    ),
                )
            for item in c.execute(
                "SELECT * FROM taxonomy_stage_names WHERE token=?", (token,)
            ).fetchall():
                c.execute(
                    "INSERT INTO taxon_names(taxon_id,language_tag,region_code,name,name_type,preferred,source) VALUES(?,?,?,?,?,?,?)",
                    (
                        db_ids[str(item["source_taxon_id"])],
                        item["language_tag"],
                        item["region_code"],
                        item["name"],
                        item["name_type"],
                        item["preferred"],
                        item["source"],
                    ),
                )
            for item in c.execute(
                "SELECT * FROM taxonomy_stage_regions WHERE token=?", (token,)
            ).fetchall():
                c.execute(
                    "INSERT OR REPLACE INTO taxon_regions(taxon_id,region_code,occurrence_status,source) VALUES(?,?,?,?)",
                    (
                        db_ids[str(item["source_taxon_id"])],
                        item["region_code"],
                        item["occurrence_status"],
                        item["source"],
                    ),
                )
            ids = tuple(db_ids.values())
            if ids:
                placeholders = ",".join("?" for _ in ids)
                c.execute(
                    f"DELETE FROM taxon_closure WHERE ancestor_taxon_id IN ({placeholders}) OR descendant_taxon_id IN ({placeholders})",
                    ids + ids,
                )
            c.execute(
                "INSERT INTO taxon_closure(ancestor_taxon_id,descendant_taxon_id,depth) SELECT id,id,0 FROM taxa WHERE source_id=?",
                (source_id,),
            )
            c.execute(
                "WITH RECURSIVE lineage(ancestor,descendant,depth) AS (SELECT parent_taxon_id,id,1 FROM taxa WHERE source_id=? AND parent_taxon_id IS NOT NULL UNION ALL SELECT t.parent_taxon_id,l.descendant,l.depth+1 FROM lineage l JOIN taxa t ON t.id=l.ancestor WHERE t.parent_taxon_id IS NOT NULL) INSERT OR IGNORE INTO taxon_closure SELECT ancestor,descendant,depth FROM lineage",
                (source_id,),
            )
            # Publish is the only visibility switch and occurs at the end.
            c.execute(
                "UPDATE taxonomy_sources SET active=0 WHERE name=? AND id!=?",
                (package.source_name, source_id),
            )
            c.execute(
                "UPDATE taxonomy_sources SET active=1,activated_at_us=? WHERE id=?",
                (now_us, source_id),
            )
            c.execute(
                "UPDATE library_info SET active_taxonomy_release_ids_json=? WHERE id=1",
                (json.dumps([source_public_id]),),
            )
            c.execute("COMMIT")

            # Successful taxonomy publication requires a fresh verified backup
            # at the next normal application shutdown.
            marker = self._factory.database_path.parent / "backup-required.json"
            marker.write_text(
                json.dumps(
                    {
                        "reason": "taxonomy_update",
                        "source_version": package.source_version,
                        "package_id": package.package_id,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            c.execute("DELETE FROM taxonomy_stage_names WHERE token=?", (token,))
            c.execute("DELETE FROM taxonomy_stage_regions WHERE token=?", (token,))
            c.execute("DELETE FROM taxonomy_stage_taxa WHERE token=?", (token,))
            return source_public_id
        except Exception:
            try:
                if c.in_transaction:
                    c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            c.close()

    def active_sources(self) -> tuple[dict[str, object], ...]:
        c = self._factory.connect()
        try:
            return tuple(
                dict(r)
                for r in c.execute(
                    "SELECT public_id,name,source_version,package_checksum,license_json,attribution_text,activated_at_us FROM taxonomy_sources WHERE active=1 ORDER BY name"
                )
            )
        finally:
            c.close()

    def _summary(self, r: sqlite3.Row) -> TaxonSummary:
        return TaxonSummary(
            r["public_id"],
            r["source_taxon_id"],
            r["scientific_name"],
            r["authorship"],
            r["rank"],
            r["status"],
            r["parent_public_id"],
            r["accepted_public_id"],
            r["preferred_name"],
            r["occurrence_status"],
        )

    def _base_sql(self) -> str:
        return """SELECT t.public_id,t.source_taxon_id,t.scientific_name,t.authorship,t.rank,t.status,p.public_id parent_public_id,a.public_id accepted_public_id,(SELECT n.name FROM taxon_names n WHERE n.taxon_id=t.id AND (? IS NULL OR n.language_tag=?) AND (? IS NULL OR n.region_code IS NULL OR n.region_code=?) ORDER BY n.preferred DESC,n.region_code IS NOT NULL DESC,n.id LIMIT 1) preferred_name,(SELECT tr.occurrence_status FROM taxon_regions tr WHERE tr.taxon_id=t.id AND tr.region_code=? LIMIT 1) occurrence_status FROM taxa t JOIN taxonomy_sources s ON s.id=t.source_id LEFT JOIN taxa p ON p.id=t.parent_taxon_id LEFT JOIN taxa a ON a.id=t.accepted_taxon_id WHERE s.active=1"""

    def search(
        self,
        text: str,
        *,
        language_tag: str | None = None,
        region_code: str | None = None,
        limit: int = 50,
    ) -> tuple[TaxonSummary, ...]:
        if not text.strip():
            return ()
        c = self._factory.connect()
        q = f"%{text.strip()}%"
        region = region_code.upper() if region_code else None
        try:
            sql = (
                self._base_sql()
                + " AND (t.scientific_name LIKE ? OR EXISTS(SELECT 1 FROM taxon_names x WHERE x.taxon_id=t.id AND x.name LIKE ?)) AND (? IS NULL OR EXISTS(SELECT 1 FROM taxon_regions rr WHERE rr.taxon_id=t.id AND rr.region_code=?)) ORDER BY CASE WHEN lower(t.scientific_name)=lower(?) THEN 0 ELSE 1 END,t.scientific_name LIMIT ?"
            )
            rows = c.execute(
                sql,
                (
                    language_tag,
                    language_tag,
                    region,
                    region,
                    region,
                    q,
                    q,
                    region,
                    region,
                    text.strip(),
                    min(max(limit, 1), 500),
                ),
            ).fetchall()
            return tuple(self._summary(r) for r in rows)
        finally:
            c.close()

    def children(
        self,
        parent_public_id: str | None,
        *,
        region_code: str | None = None,
        language_tag: str | None = None,
        after_name: str | None = None,
        limit: int = 200,
    ) -> TaxonPage:
        c = self._factory.connect()
        region = region_code.upper() if region_code else None
        limit = min(max(limit, 1), 500)
        try:
            sql = (
                self._base_sql()
                + " AND ((? IS NULL AND t.parent_taxon_id IS NULL) OR p.public_id=?) AND (? IS NULL OR t.scientific_name>?) AND (? IS NULL OR EXISTS(SELECT 1 FROM taxon_regions rr WHERE rr.taxon_id=t.id AND rr.region_code=?)) ORDER BY t.scientific_name,t.id LIMIT ?"
            )
            rows = c.execute(
                sql,
                (
                    language_tag,
                    language_tag,
                    region,
                    region,
                    region,
                    parent_public_id,
                    parent_public_id,
                    after_name,
                    after_name,
                    region,
                    region,
                    limit + 1,
                ),
            ).fetchall()
            items = tuple(self._summary(r) for r in rows[:limit])
            return TaxonPage(
                items, items[-1].scientific_name if len(rows) > limit and items else None
            )
        finally:
            c.close()

    def detail(
        self, public_id: str, *, language_tag: str | None = None, region_code: str | None = None
    ) -> TaxonSummary:
        c = self._factory.connect()
        region = region_code.upper() if region_code else None
        try:
            r = c.execute(
                self._base_sql() + " AND t.public_id=?",
                (language_tag, language_tag, region, region, region, public_id),
            ).fetchone()
            if r is None:
                raise KeyError(public_id)
            return self._summary(r)
        finally:
            c.close()

    def verify_closure(self, source_public_id: str) -> tuple[int, int]:
        c = self._factory.connect()
        try:
            expected = int(
                c.execute(
                    "WITH RECURSIVE x(a,d) AS (SELECT id,id FROM taxa WHERE source_id=(SELECT id FROM taxonomy_sources WHERE public_id=?) UNION ALL SELECT t.parent_taxon_id,x.d FROM x JOIN taxa t ON t.id=x.a WHERE t.parent_taxon_id IS NOT NULL) SELECT COUNT(*) FROM x",
                    (source_public_id,),
                ).fetchone()[0]
            )
            actual = int(
                c.execute(
                    "SELECT COUNT(*) FROM taxon_closure tc JOIN taxa t ON t.id=tc.descendant_taxon_id WHERE t.source_id=(SELECT id FROM taxonomy_sources WHERE public_id=?)",
                    (source_public_id,),
                ).fetchone()[0]
            )
            return expected, actual
        finally:
            c.close()

    def rebuild_closure(self, source_public_id: str) -> None:
        with SqliteUnitOfWork(self._factory) as u:
            c = u.connection
            assert c is not None
            sid = c.execute(
                "SELECT id FROM taxonomy_sources WHERE public_id=?", (source_public_id,)
            ).fetchone()
            if sid is None:
                raise KeyError(source_public_id)
            source_id = int(sid[0])
            c.execute(
                "DELETE FROM taxon_closure WHERE descendant_taxon_id IN (SELECT id FROM taxa WHERE source_id=?)",
                (source_id,),
            )
            c.execute(
                "INSERT INTO taxon_closure SELECT id,id,0 FROM taxa WHERE source_id=?", (source_id,)
            )
            c.execute(
                "WITH RECURSIVE lineage(ancestor,descendant,depth) AS (SELECT parent_taxon_id,id,1 FROM taxa WHERE source_id=? AND parent_taxon_id IS NOT NULL UNION ALL SELECT t.parent_taxon_id,l.descendant,l.depth+1 FROM lineage l JOIN taxa t ON t.id=l.ancestor WHERE t.parent_taxon_id IS NOT NULL) INSERT INTO taxon_closure SELECT ancestor,descendant,depth FROM lineage",
                (source_id,),
            )
            u.commit()


class SqliteObservationAdapter:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def _view(self, c: sqlite3.Connection, public_id: str) -> ObservationView:
        r = c.execute(
            """SELECT o.public_id,a.public_id asset_public_id,o.revision,o.observation_type,o.confirmation_state,t.public_id taxon_public_id,u.public_id user_taxon_public_id,COALESCE(t.scientific_name,u.display_name) display_name,o.life_stage,o.sex,o.count,o.behavior,o.notes,roi.public_id roi_public_id FROM observations o JOIN assets a ON a.id=o.asset_id LEFT JOIN taxa t ON t.id=o.taxon_id LEFT JOIN user_taxa u ON u.id=o.user_taxon_id LEFT JOIN regions_of_interest roi ON roi.id=o.region_of_interest_id WHERE o.public_id=?""",
            (public_id,),
        ).fetchone()
        if r is None:
            raise KeyError(public_id)
        return ObservationView(**dict(r))

    def create(
        self,
        *,
        public_id: str,
        asset_public_id: str,
        draft: ObservationDraft,
        now_us: int,
        source: str = "user",
    ) -> ObservationView:
        draft.validate()
        with SqliteUnitOfWork(self._factory) as u:
            c = u.connection
            assert c is not None
            c.execute(
                """INSERT INTO observations(public_id,asset_id,taxon_id,user_taxon_id,observation_type,life_stage,sex,count,behavior,notes,confirmation_state,source,region_of_interest_id,created_at_us,modified_at_us,revision) SELECT ?,a.id,t.id,ut.id,?,?,?,?,?,?,?,?,roi.id,?,?,1 FROM assets a LEFT JOIN taxa t ON t.public_id=? LEFT JOIN user_taxa ut ON ut.public_id=? LEFT JOIN regions_of_interest roi ON roi.public_id=? WHERE a.public_id=?""",
                (
                    public_id,
                    draft.observation_type.value,
                    draft.life_stage,
                    draft.sex,
                    draft.count,
                    draft.behavior,
                    draft.notes,
                    draft.confirmation_state.value,
                    source,
                    now_us,
                    now_us,
                    draft.taxon_public_id,
                    draft.user_taxon_public_id,
                    draft.roi_public_id,
                    asset_public_id,
                ),
            )
            if c.execute("SELECT changes()").fetchone()[0] != 1:
                raise KeyError(asset_public_id)
            oid = int(
                c.execute("SELECT id FROM observations WHERE public_id=?", (public_id,)).fetchone()[
                    0
                ]
            )
            snapshot = json.dumps(asdict(draft), default=str, sort_keys=True, separators=(",", ":"))
            c.execute(
                "INSERT INTO observation_revisions(observation_id,revision,snapshot_json,changed_at_us) VALUES(?,?,?,?)",
                (oid, 1, snapshot, now_us),
            )
            view = self._view(c, public_id)
            u.commit()
            return view

    def update(
        self, *, public_id: str, expected_revision: int, draft: ObservationDraft, now_us: int
    ) -> ObservationView:
        draft.validate()
        with SqliteUnitOfWork(self._factory) as u:
            c = u.connection
            assert c is not None
            c.execute(
                """UPDATE observations SET taxon_id=(SELECT id FROM taxa WHERE public_id=?),user_taxon_id=(SELECT id FROM user_taxa WHERE public_id=?),observation_type=?,life_stage=?,sex=?,count=?,behavior=?,notes=?,confirmation_state=?,region_of_interest_id=(SELECT id FROM regions_of_interest WHERE public_id=?),modified_at_us=?,revision=revision+1 WHERE public_id=? AND revision=?""",
                (
                    draft.taxon_public_id,
                    draft.user_taxon_public_id,
                    draft.observation_type.value,
                    draft.life_stage,
                    draft.sex,
                    draft.count,
                    draft.behavior,
                    draft.notes,
                    draft.confirmation_state.value,
                    draft.roi_public_id,
                    now_us,
                    public_id,
                    expected_revision,
                ),
            )
            if c.execute("SELECT changes()").fetchone()[0] != 1:
                raise RuntimeError("observation revision conflict")
            row = c.execute(
                "SELECT id,revision FROM observations WHERE public_id=?", (public_id,)
            ).fetchone()
            snapshot = json.dumps(asdict(draft), default=str, sort_keys=True, separators=(",", ":"))
            c.execute(
                "INSERT INTO observation_revisions VALUES(NULL,?,?,?,?)",
                (row["id"], row["revision"], snapshot, now_us),
            )
            view = self._view(c, public_id)
            u.commit()
            return view

    def list_for_asset(self, asset_public_id: str) -> tuple[ObservationView, ...]:
        c = self._factory.connect()
        try:
            ids = [
                r[0]
                for r in c.execute(
                    "SELECT o.public_id FROM observations o JOIN assets a ON a.id=o.asset_id WHERE a.public_id=? ORDER BY o.created_at_us,o.id",
                    (asset_public_id,),
                )
            ]
            return tuple(self._view(c, x) for x in ids)
        finally:
            c.close()

    def create_roi(
        self, *, public_id: str, asset_public_id: str, draft: RegionOfInterestDraft, now_us: int
    ) -> str:
        draft.validate()
        payload = json.dumps(draft.coordinates, sort_keys=True, separators=(",", ":"))
        with SqliteUnitOfWork(self._factory) as u:
            c = u.connection
            assert c is not None
            c.execute(
                "INSERT INTO regions_of_interest(public_id,asset_id,shape_type,coordinates_json,label,created_source,created_at_us,modified_at_us) SELECT ?,id,?,?,?,?,?,? FROM assets WHERE public_id=?",
                (
                    public_id,
                    draft.shape_type,
                    payload,
                    draft.label,
                    "user",
                    now_us,
                    now_us,
                    asset_public_id,
                ),
            )
            if c.execute("SELECT changes()").fetchone()[0] != 1:
                raise KeyError(asset_public_id)
            u.commit()
            return public_id


class SqliteUserTaxonAdapter:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def create(
        self,
        *,
        public_id: str,
        display_name: str,
        scientific_name: str | None,
        rank: str | None,
        now_us: int,
    ) -> None:
        with SqliteUnitOfWork(self._factory) as u:
            assert u.connection is not None
            u.connection.execute(
                "INSERT INTO user_taxa(public_id,scientific_name,display_name,rank,created_at_us,modified_at_us) VALUES(?,?,?,?,?,?)",
                (public_id, scientific_name, display_name, rank, now_us, now_us),
            )
            u.commit()

    def map_to_taxon(
        self, *, user_taxon_public_id: str, taxon_public_id: str | None, now_us: int
    ) -> None:
        with SqliteUnitOfWork(self._factory) as u:
            c = u.connection
            assert c is not None
            c.execute(
                "UPDATE user_taxa SET mapped_taxon_id=(SELECT id FROM taxa WHERE public_id=?),modified_at_us=? WHERE public_id=?",
                (taxon_public_id, now_us, user_taxon_public_id),
            )
            if c.execute("SELECT changes()").fetchone()[0] != 1:
                raise KeyError(user_taxon_public_id)
            u.commit()
