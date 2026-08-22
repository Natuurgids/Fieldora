"""Shared, lazily activated taxonomy-reference subsystem."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from natureai_next.domain.taxonomy import TaxonKnowledgeProfile
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.subsystems.migrations.taxonomy_v001_reference import (
    MIGRATION as V001,
)
from natureai_next.infrastructure.subsystems.migrations.taxonomy_v002_library_links import (
    MIGRATION as V002,
)
from natureai_next.infrastructure.subsystems.migrations.taxonomy_v003_authoritative_packages import (
    MIGRATION as V003,
)
from natureai_next.infrastructure.subsystems.migrations.taxonomy_v004_preferences import (
    MIGRATION as V004,
)
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseDescriptor

TAXONOMY_SUBSYSTEM_KEY = "taxonomy.reference"
TAXONOMY_MIGRATIONS = (V001, V002, V003, V004)


def taxonomy_descriptor(database_path: Path) -> SubsystemDatabaseDescriptor:
    return SubsystemDatabaseDescriptor(TAXONOMY_SUBSYSTEM_KEY, database_path, TAXONOMY_MIGRATIONS)


@dataclass(frozen=True, slots=True)
class ReferenceTaxon:
    public_id: str
    source_taxon_id: str
    scientific_name: str
    rank: str
    status: str = "accepted"
    authorship: str | None = None
    parent_public_id: str | None = None
    accepted_public_id: str | None = None
    kingdom: str | None = None
    major_group: str | None = None
    extinct: bool = False


@dataclass(frozen=True, slots=True)
class TaxonomyPreferences:
    language_tag: str | None = None
    region_code: str | None = None
    prefer_common_name: bool = True


@dataclass(frozen=True, slots=True)
class TaxonomyDatasetSummary:
    public_id: str
    source_name: str
    source_version: str
    license_name: str
    attribution: str
    active: bool
    enabled: bool


class TaxonomyReferenceCatalog:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def preferences(self) -> TaxonomyPreferences:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT language_tag,region_code,prefer_common_name FROM taxonomy_preferences WHERE id=1"
            ).fetchone()
            return TaxonomyPreferences(
                None if row is None else row[0],
                None if row is None else row[1],
                True if row is None else bool(row[2]),
            )
        finally:
            connection.close()

    def set_preferences(
        self,
        *,
        language_tag: str | None,
        region_code: str | None,
        prefer_common_name: bool,
        updated_at_us: int,
    ) -> TaxonomyPreferences:
        language = language_tag.strip().lower() if language_tag and language_tag.strip() else None
        region = region_code.strip().upper() if region_code and region_code.strip() else None
        connection = self._factory.connect()
        try:
            connection.execute(
                "UPDATE taxonomy_preferences SET language_tag=?,region_code=?,prefer_common_name=?,updated_at_us=? WHERE id=1",
                (language, region, int(prefer_common_name), updated_at_us),
            )
        finally:
            connection.close()
        return TaxonomyPreferences(language, region, prefer_common_name)

    def datasets(self) -> tuple[TaxonomyDatasetSummary, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT public_id,source_name,source_version,license_name,attribution,active,enabled FROM taxonomy_datasets ORDER BY source_name,installed_at_us DESC"
            ).fetchall()
            return tuple(
                TaxonomyDatasetSummary(r[0], r[1], r[2], r[3], r[4], bool(r[5]), bool(r[6]))
                for r in rows
            )
        finally:
            connection.close()

    def set_dataset_enabled(self, public_id: str, *, enabled: bool, changed_at_us: int) -> None:
        connection = self._factory.connect()
        try:
            cursor = connection.execute(
                "UPDATE taxonomy_datasets SET enabled=?,disabled_at_us=? WHERE public_id=?",
                (int(enabled), None if enabled else changed_at_us, public_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(public_id)
        finally:
            connection.close()

    def install_dataset(
        self,
        *,
        public_id: str,
        source_name: str,
        source_version: str,
        checksum_sha256: str,
        license_name: str,
        attribution: str,
        installed_at_us: int,
        taxa: tuple[ReferenceTaxon, ...],
        license_url: str | None = None,
        redistribution_allowed: bool = False,
        source_url: str | None = None,
        package_schema_version: int = 1,
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE taxonomy_datasets SET active=0 WHERE source_name=?", (source_name,)
            )
            cursor = connection.execute(
                "INSERT INTO taxonomy_datasets(public_id,source_name,source_version,checksum_sha256,license_name,attribution,installed_at_us,active,license_url,redistribution_allowed,source_url,package_schema_version) VALUES(?,?,?,?,?,?,?,1,?,?,?,?)",
                (
                    public_id,
                    source_name,
                    source_version,
                    checksum_sha256,
                    license_name,
                    attribution,
                    installed_at_us,
                    license_url,
                    int(redistribution_allowed),
                    source_url,
                    package_schema_version,
                ),
            )
            dataset_id = int(cursor.lastrowid)
            connection.executemany(
                "INSERT INTO reference_taxa(dataset_id,public_id,source_taxon_id,scientific_name,authorship,rank,status,parent_public_id,accepted_public_id,kingdom,major_group,extinct) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                tuple(
                    (
                        dataset_id,
                        item.public_id,
                        item.source_taxon_id,
                        item.scientific_name,
                        item.authorship,
                        item.rank,
                        item.status,
                        item.parent_public_id,
                        item.accepted_public_id,
                        item.kingdom,
                        item.major_group,
                        int(item.extinct),
                    )
                    for item in taxa
                ),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def install_verified_package(
        self, package, *, installed_at_us: int, source_url: str | None = None
    ) -> str:
        """Install a verified package into the shared reference catalog atomically."""
        import hashlib

        source_to_public = {
            item.source_taxon_id: "ref-"
            + hashlib.sha256(f"{package.source_name}|{item.source_taxon_id}".encode()).hexdigest()[
                :32
            ]
            for item in package.taxa
        }
        taxa = tuple(
            ReferenceTaxon(
                public_id=source_to_public[item.source_taxon_id],
                source_taxon_id=item.source_taxon_id,
                scientific_name=item.scientific_name,
                rank=item.rank,
                status=item.status.value,
                authorship=item.authorship,
                parent_public_id=source_to_public.get(item.parent_source_taxon_id),
                accepted_public_id=source_to_public.get(item.accepted_source_taxon_id),
                kingdom=item.kingdom,
                major_group=item.major_group,
                extinct=item.extinct,
            )
            for item in package.taxa
        )
        self.install_dataset(
            public_id=package.package_id,
            source_name=package.source_name,
            source_version=package.source_version,
            checksum_sha256=package.checksum,
            license_name=package.license.name,
            license_url=package.license.url,
            redistribution_allowed=package.license.redistribution_allowed,
            attribution=package.attribution_text,
            source_url=source_url,
            installed_at_us=installed_at_us,
            taxa=taxa,
        )
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.executemany(
                "INSERT OR IGNORE INTO reference_taxon_names(taxon_public_id,name,name_type,language_tag,region_code,preferred,source,source_record_id,verification_state) VALUES(?,?,?,?,?,?,?,?,?)",
                tuple(
                    (
                        source_to_public[n.source_taxon_id],
                        n.name,
                        n.name_type,
                        n.language_tag,
                        n.region_code,
                        int(n.preferred),
                        n.source,
                        None,
                        "source",
                    )
                    for n in package.names
                    if n.source_taxon_id in source_to_public
                ),
            )
            connection.executemany(
                "INSERT OR IGNORE INTO reference_taxon_distributions(taxon_public_id,region_code,occurrence_status,establishment_means,source) VALUES(?,?,?,?,?)",
                tuple(
                    (
                        source_to_public[r.source_taxon_id],
                        r.region_code.upper(),
                        r.occurrence_status,
                        None,
                        r.source,
                    )
                    for r in package.regions
                    if r.source_taxon_id in source_to_public
                ),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return package.package_id

    def map_ai_label(
        self,
        *,
        model_family: str,
        model_version: str,
        label: str,
        reference_taxon_public_id: str,
        source: str,
        mapped_at_us: int,
        mapping_state: str = "confirmed",
        notes: str | None = None,
    ) -> None:
        if mapping_state not in {"confirmed", "probable", "rejected"}:
            raise ValueError("unsupported mapping state")
        self.profile(reference_taxon_public_id)
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO ai_taxon_label_mappings(model_family,model_version,label,reference_taxon_public_id,mapping_state,source,mapped_at_us,notes) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(model_family,model_version,label) DO UPDATE SET reference_taxon_public_id=excluded.reference_taxon_public_id,mapping_state=excluded.mapping_state,source=excluded.source,mapped_at_us=excluded.mapped_at_us,notes=excluded.notes",
                (
                    model_family.strip(),
                    model_version.strip(),
                    label.strip(),
                    reference_taxon_public_id,
                    mapping_state,
                    source,
                    mapped_at_us,
                    notes,
                ),
            )
        finally:
            connection.close()

    def resolve_ai_label(self, *, model_family: str, model_version: str, label: str) -> str | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT reference_taxon_public_id FROM ai_taxon_label_mappings WHERE model_family=? AND model_version=? AND label=? AND mapping_state!='rejected'",
                (model_family.strip(), model_version.strip(), label.strip()),
            ).fetchone()
            return None if row is None else str(row[0])
        finally:
            connection.close()

    def add_name(
        self,
        *,
        taxon_public_id: str,
        name: str,
        name_type: str,
        source: str,
        language_tag: str | None = None,
        region_code: str | None = None,
        preferred: bool = False,
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO reference_taxon_names(taxon_public_id,name,name_type,language_tag,region_code,preferred,source) VALUES(?,?,?,?,?,?,?)",
                (
                    taxon_public_id,
                    name,
                    name_type,
                    language_tag,
                    region_code,
                    int(preferred),
                    source,
                ),
            )
        finally:
            connection.close()

    def add_fact(
        self,
        *,
        taxon_public_id: str,
        fact_type: str,
        value_text: str,
        source: str,
        language_tag: str | None = None,
        region_code: str | None = None,
        source_url: str | None = None,
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO reference_taxon_facts(taxon_public_id,fact_type,value_text,language_tag,region_code,source,source_url) VALUES(?,?,?,?,?,?,?)",
                (
                    taxon_public_id,
                    fact_type,
                    value_text,
                    language_tag,
                    region_code,
                    source,
                    source_url,
                ),
            )
        finally:
            connection.close()

    def add_distribution(
        self,
        *,
        taxon_public_id: str,
        region_code: str,
        source: str,
        occurrence_status: str | None = None,
        establishment_means: str | None = None,
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO reference_taxon_distributions(taxon_public_id,region_code,occurrence_status,establishment_means,source) VALUES(?,?,?,?,?)",
                (
                    taxon_public_id,
                    region_code.upper(),
                    occurrence_status,
                    establishment_means,
                    source,
                ),
            )
        finally:
            connection.close()

    def add_link(
        self,
        *,
        taxon_public_id: str,
        relation_type: str,
        title: str,
        source: str,
        external_id: str | None = None,
        url: str | None = None,
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO reference_taxon_links(taxon_public_id,relation_type,external_id,title,url,source) VALUES(?,?,?,?,?,?)",
                (taxon_public_id, relation_type, external_id, title, url, source),
            )
        finally:
            connection.close()

    def link_library_taxon(
        self,
        *,
        library_public_id: str,
        local_taxon_public_id: str,
        reference_taxon_public_id: str,
        source: str,
        linked_at_us: int,
        link_state: str = "confirmed",
        notes: str | None = None,
    ) -> None:
        if link_state not in {"confirmed", "probable", "rejected"}:
            raise ValueError("unsupported link state")
        # Validate the reference identity before recording a cross-database link.
        self.profile(reference_taxon_public_id)
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO library_taxon_links(library_public_id,local_taxon_public_id,reference_taxon_public_id,link_state,source,linked_at_us,notes) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(library_public_id,local_taxon_public_id) DO UPDATE SET reference_taxon_public_id=excluded.reference_taxon_public_id,link_state=excluded.link_state,source=excluded.source,linked_at_us=excluded.linked_at_us,notes=excluded.notes",
                (
                    library_public_id,
                    local_taxon_public_id,
                    reference_taxon_public_id,
                    link_state,
                    source,
                    linked_at_us,
                    notes,
                ),
            )
        finally:
            connection.close()

    def resolve_reference_taxon(
        self, *, library_public_id: str, local_taxon_public_id: str
    ) -> str | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT reference_taxon_public_id FROM library_taxon_links WHERE library_public_id=? AND local_taxon_public_id=? AND link_state!='rejected'",
                (library_public_id, local_taxon_public_id),
            ).fetchone()
            return None if row is None else str(row[0])
        finally:
            connection.close()

    def local_taxa_for_reference(
        self, *, library_public_id: str, reference_taxon_public_id: str
    ) -> tuple[str, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            return tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT local_taxon_public_id FROM library_taxon_links WHERE library_public_id=? AND reference_taxon_public_id=? AND link_state!='rejected' ORDER BY linked_at_us",
                    (library_public_id, reference_taxon_public_id),
                )
            )
        finally:
            connection.close()

    def search(self, text: str, *, limit: int = 50) -> tuple[ReferenceTaxon, ...]:
        target = text.strip()
        if not target:
            return ()
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT DISTINCT t.public_id,t.source_taxon_id,t.scientific_name,t.rank,t.status,t.authorship,t.parent_public_id,t.accepted_public_id,t.kingdom,t.major_group,t.extinct "
                "FROM reference_taxa t JOIN taxonomy_datasets d ON d.id=t.dataset_id AND d.active=1 AND d.enabled=1 "
                "LEFT JOIN reference_taxon_names n ON n.taxon_public_id=t.public_id "
                "WHERE t.scientific_name LIKE ? OR n.name LIKE ? ORDER BY t.scientific_name LIMIT ?",
                (f"%{target}%", f"%{target}%", limit),
            ).fetchall()
            return tuple(ReferenceTaxon(**dict(row)) for row in rows)
        finally:
            connection.close()

    def profile(
        self, public_id: str, *, language_tag: str | None = None, region_code: str | None = None
    ) -> TaxonKnowledgeProfile:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT t.public_id,t.scientific_name,t.authorship,t.rank,t.status FROM reference_taxa t JOIN taxonomy_datasets d ON d.id=t.dataset_id AND d.active=1 AND d.enabled=1 WHERE t.public_id=?",
                (public_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown reference taxon: {public_id}")
            prefs = self.preferences()
            language = language_tag if language_tag is not None else prefs.language_tag
            region = region_code if region_code is not None else prefs.region_code
            region = region.upper() if region else None
            names = tuple(
                r[0]
                for r in connection.execute(
                    "SELECT name FROM reference_taxon_names WHERE taxon_public_id=? "
                    "ORDER BY CASE WHEN ? IS NOT NULL AND lower(language_tag)=lower(?) THEN 0 ELSE 1 END, "
                    "CASE WHEN ? IS NOT NULL AND region_code=? THEN 0 WHEN region_code IS NULL THEN 1 ELSE 2 END, preferred DESC,name",
                    (public_id, language, language, region, region),
                )
            )
            facts = tuple(
                dict(r)
                for r in connection.execute(
                    "SELECT fact_type,value_text,language_tag,region_code,source,source_url FROM reference_taxon_facts WHERE taxon_public_id=? ORDER BY fact_type,id",
                    (public_id,),
                )
            )
            distributions = tuple(
                dict(r)
                for r in connection.execute(
                    "SELECT region_code,occurrence_status,establishment_means,source FROM reference_taxon_distributions WHERE taxon_public_id=? ORDER BY region_code,source",
                    (public_id,),
                )
            )
            links = tuple(
                dict(r)
                for r in connection.execute(
                    "SELECT relation_type,external_id,title,url,source FROM reference_taxon_links WHERE taxon_public_id=? ORDER BY relation_type,title",
                    (public_id,),
                )
            )
            return TaxonKnowledgeProfile(
                public_id=row["public_id"],
                scientific_name=row["scientific_name"],
                authorship=row["authorship"],
                rank=row["rank"],
                status=row["status"],
                preferred_names=names,
                facts=facts,
                distributions=distributions,
                links=links,
            )
        finally:
            connection.close()
