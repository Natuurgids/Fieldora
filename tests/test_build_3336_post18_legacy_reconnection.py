import sqlite3
from pathlib import Path

from natureai_next.application.ai_setup import BIOCLIP_REVISION
from natureai_next.application.external_taxonomy import GbifTaxonomyLibrary


def test_gbif_browser_reads_importer_schema(tmp_path: Path):
    db = tmp_path / "gbif.active.sqlite3"
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE taxa(source_taxon_id TEXT PRIMARY KEY, scientific_name TEXT, authorship TEXT, rank TEXT, status TEXT, parent_source_taxon_id TEXT, accepted_source_taxon_id TEXT, kingdom TEXT, major_group TEXT, taxon_class TEXT, taxon_order TEXT, family TEXT);
    CREATE TABLE taxon_names(source_taxon_id TEXT, name TEXT, name_type TEXT, language_tag TEXT, preferred INTEGER, source TEXT);
    INSERT INTO taxa VALUES('1','Quercus robur',NULL,'species','accepted',NULL,NULL,'Plantae','Tracheophyta','Magnoliopsida','Fagales','Fagaceae');
    INSERT INTO taxon_names VALUES('1','English oak','vernacular','en',1,'GBIF');
    """)
    con.commit()
    con.close()
    source = GbifTaxonomyLibrary(tmp_path)
    rows = source.search("oak")
    assert rows and rows[0].scientific_name == "Quercus robur"
    assert rows[0].vernacular_name == "English oak"


def test_obsolete_names_only_schema_is_rejected(tmp_path: Path):
    db = tmp_path / "gbif.active.sqlite3"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE names(name TEXT)")
    con.commit()
    con.close()
    source = GbifTaxonomyLibrary(tmp_path)
    try:
        source.search("tree")
    except RuntimeError as exc:
        assert "taxa and taxon_names" in str(exc)
    else:
        raise AssertionError("obsolete schema should not be queried")


def test_bioclip_revision_is_real_pinned_model_revision():
    assert BIOCLIP_REVISION == "1f135cb2599b3c076efaa7a101f47b40e068878c"
