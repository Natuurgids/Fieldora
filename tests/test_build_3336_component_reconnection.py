import json
import sqlite3
from pathlib import Path

from natureai_next.application.components import ResourceComponentRegistry
from natureai_next.application.external_taxonomy import GbifTaxonomyLibrary


def test_gbif_uses_published_registry_and_taxon_names_schema(tmp_path: Path):
    root = tmp_path / "taxonomy-sources"
    root.mkdir()
    database = root / "gbif-source-test.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
        CREATE TABLE taxa(source_taxon_id TEXT PRIMARY KEY, scientific_name TEXT, authorship TEXT,
          rank TEXT, status TEXT, parent_source_taxon_id TEXT, accepted_source_taxon_id TEXT,
          kingdom TEXT, major_group TEXT, taxon_class TEXT, taxon_order TEXT, family TEXT);
        CREATE TABLE taxon_names(source_taxon_id TEXT, name TEXT, name_type TEXT,
          language_tag TEXT, preferred INTEGER, source TEXT);
        INSERT INTO taxa VALUES('1','Buteo buteo',NULL,'species','accepted',NULL,NULL,
          'Animalia','Aves','Aves','Accipitriformes','Accipitridae');
        INSERT INTO taxon_names VALUES('1','Common buzzard','vernacular','en',1,'GBIF');
        """)
    (root / "sources.json").write_text(
        json.dumps({"active": {"gbif": {"database": database.name}}}), encoding="utf-8"
    )
    source = GbifTaxonomyLibrary(root)
    assert source.database == database
    results = source.search("buzzard")
    assert results and results[0].scientific_name == "Buteo buteo"
    assert results[0].vernacular_name == "Common buzzard"


def test_component_switches_persist_without_removing_resources(tmp_path: Path):
    path = tmp_path / "components.json"
    registry = ResourceComponentRegistry(path)
    assert registry.enabled("gbif") and registry.enabled("bioclip")
    registry.set_enabled("bioclip", False)
    assert not ResourceComponentRegistry(path).enabled("bioclip")
    assert ResourceComponentRegistry(path).enabled("gbif")
