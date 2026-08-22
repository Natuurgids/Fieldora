"""Independent GBIF taxonomy browsing and lightweight library enrichment links."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExternalTaxon:
    source_taxon_id: str
    scientific_name: str
    vernacular_name: str | None
    rank: str
    kingdom: str | None
    taxon_class: str | None
    taxon_order: str | None
    family: str | None


class GbifTaxonomyLibrary:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or self._default_root()).expanduser().resolve()
        self.database = self._resolve_database()

    @staticmethod
    def _default_root() -> Path:
        override = os.getenv("APERTURE_TAXONOMY_ROOT") or os.getenv("NATUREAI_TAXONOMY_ROOT")
        if override:
            return Path(override)
        base = Path(os.getenv("LOCALAPPDATA", Path.home()))
        candidates = (
            base / "NatureAI" / "NatureAI Next" / "taxonomy-sources",
            base / "Aperture" / "taxonomy-sources",
        )
        for candidate in candidates:
            if (candidate / "sources.json").is_file() or (
                candidate / "gbif.active.sqlite3"
            ).is_file():
                return candidate
        return candidates[0]

    def _resolve_database(self) -> Path:
        """Resolve the database published by the isolated GBIF importer."""
        registry = self.root / "sources.json"
        try:
            payload = json.loads(registry.read_text(encoding="utf-8"))
            configured = payload.get("active", {}).get("gbif", {}).get("database")
            if configured:
                candidate = self.root / str(configured)
                if candidate.is_file():
                    return candidate
        except (OSError, ValueError, TypeError):
            pass
        legacy = self.root / "gbif.active.sqlite3"
        if legacy.is_file():
            return legacy
        candidates = sorted(
            self.root.glob("gbif-*.sqlite3"), key=lambda item: item.stat().st_mtime_ns, reverse=True
        )
        return candidates[0] if candidates else legacy

    @staticmethod
    def _schema(connection: sqlite3.Connection) -> tuple[set[str], set[str], set[str]]:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        taxa_columns = (
            {str(row[1]) for row in connection.execute("PRAGMA table_info(taxa)")}
            if "taxa" in tables
            else set()
        )
        name_columns = (
            {str(row[1]) for row in connection.execute("PRAGMA table_info(taxon_names)")}
            if "taxon_names" in tables
            else set()
        )
        required_taxa = {"source_taxon_id", "scientific_name", "rank"}
        required_names = {"source_taxon_id", "name", "name_type"}
        if not required_taxa.issubset(taxa_columns) or not required_names.issubset(name_columns):
            raise RuntimeError(
                "GBIF database schema is not recognized. Expected importer tables "
                f"taxa and taxon_names; found tables: {', '.join(sorted(tables)) or 'none'}"
            )
        return tables, taxa_columns, name_columns

    def identity(self) -> str:
        if not self.database.is_file():
            return "missing"
        stat = self.database.stat()
        return hashlib.sha256(
            f"{self.database}:{stat.st_size}:{stat.st_mtime_ns}".encode()
        ).hexdigest()

    def search(self, text: str, *, limit: int = 250) -> tuple[ExternalTaxon, ...]:
        if not self.database.is_file():
            return ()
        value = " ".join(text.split())
        pattern = f"%{value.casefold()}%"
        uri = f"file:{self.database.as_posix()}?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True, timeout=5.0) as con:
            con.execute("PRAGMA query_only=ON")
            _tables, taxa_columns, name_columns = self._schema(con)

            def optional(column) -> str:
                return f"t.{column}" if column in taxa_columns else "NULL"

            sql = f"""
                SELECT t.source_taxon_id,t.scientific_name,
                       (SELECT n.name FROM taxon_names n WHERE n.source_taxon_id=t.source_taxon_id AND n.name_type='vernacular' ORDER BY {"n.preferred DESC," if "preferred" in name_columns else ""} n.rowid LIMIT 1),
                       t.rank,{optional("kingdom")},{optional("taxon_class")},{optional("taxon_order")},{optional("family")}
                FROM taxa t
                WHERE (?='' OR lower(t.scientific_name) LIKE ? OR EXISTS(
                    SELECT 1 FROM taxon_names n2 WHERE n2.source_taxon_id=t.source_taxon_id AND lower(n2.name) LIKE ?))
                ORDER BY CASE WHEN lower(t.scientific_name)=? THEN 0 WHEN lower(t.scientific_name) LIKE ? THEN 1 ELSE 2 END,
                         t.scientific_name COLLATE NOCASE
                LIMIT ?
            """
            rows = con.execute(
                sql, (value, pattern, pattern, value.casefold(), value.casefold() + "%", limit)
            ).fetchall()
        return tuple(ExternalTaxon(*(None if x is None else str(x) for x in row)) for row in rows)


class ExternalTaxonomyEnrichmentStore:
    """Stores only links/snapshots in the Aperture DB; GBIF rows stay external."""

    def __init__(self, library_database: Path) -> None:
        self.database = library_database

    def apply(
        self, asset_public_ids: tuple[str, ...], taxon: ExternalTaxon, *, source_identity: str
    ) -> int:
        if not asset_public_ids:
            return 0
        now = time.time_ns() // 1000
        con = sqlite3.connect(self.database)
        try:
            con.execute("PRAGMA foreign_keys=ON")
            count = 0
            for asset_id in asset_public_ids:
                public_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL, f"natureai-next:external-taxonomy:gbif:{asset_id}"
                    )
                )
                con.execute(
                    """INSERT INTO asset_taxonomy_enrichments(
                    public_id,asset_id,source_key,source_taxon_id,scientific_name,vernacular_name,rank,source_database_identity,created_at_us,modified_at_us)
                    SELECT ?,a.id,'gbif',?,?,?,?,?,?,? FROM assets a WHERE a.public_id=?
                    ON CONFLICT(asset_id,source_key) DO UPDATE SET
                      source_taxon_id=excluded.source_taxon_id,scientific_name=excluded.scientific_name,
                      vernacular_name=excluded.vernacular_name,rank=excluded.rank,
                      source_database_identity=excluded.source_database_identity,modified_at_us=excluded.modified_at_us""",
                    (
                        public_id,
                        taxon.source_taxon_id,
                        taxon.scientific_name,
                        taxon.vernacular_name,
                        taxon.rank,
                        source_identity,
                        now,
                        now,
                        asset_id,
                    ),
                )
                count += int(con.execute("SELECT changes()").fetchone()[0] > 0)
            con.commit()
            return count
        finally:
            con.close()
