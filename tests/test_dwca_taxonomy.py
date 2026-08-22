import zipfile
from pathlib import Path

from natureai_next.application.dwca_taxonomy import DwcaTaxonomyImportService

META = """<?xml version="1.0" encoding="UTF-8"?>
<archive xmlns="http://rs.tdwg.org/dwc/text/">
  <core encoding="UTF-8" fieldsTerminatedBy="\\t" fieldsEnclosedBy="&quot;" ignoreHeaderLines="1" rowType="http://rs.tdwg.org/dwc/terms/Occurrence">
    <files><location>occurrence.txt</location></files>
    <id index="0"/>
    <field index="1" term="http://rs.tdwg.org/dwc/terms/taxonKey"/>
    <field index="2" term="http://rs.tdwg.org/dwc/terms/scientificName"/>
    <field index="3" term="http://rs.tdwg.org/dwc/terms/taxonRank"/>
    <field index="4" term="http://rs.tdwg.org/dwc/terms/kingdom"/>
  </core>
</archive>
"""


def test_dwca_taxonomy_reads_gbif_occurrence_core(tmp_path: Path) -> None:
    archive = tmp_path / "gbif.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("meta.xml", META)
        z.writestr(
            "occurrence.txt",
            "id\ttaxonKey\tscientificName\ttaxonRank\tkingdom\n1\t2878688\tBellis perennis\tSPECIES\tPlantae\n2\t2878688\tBellis perennis\tSPECIES\tPlantae\n",
        )
    taxa, names = DwcaTaxonomyImportService._read_archive(archive)
    assert len(taxa) == 1
    assert taxa[0]["source_taxon_id"] == "2878688"
    assert taxa[0]["scientific_name"] == "Bellis perennis"
    assert taxa[0]["kingdom"] == "Plantae"
    assert len(names) == 1


META_WITHOUT_INDEXES = """<?xml version="1.0" encoding="UTF-8"?>
<archive xmlns="http://rs.tdwg.org/dwc/text/">
  <core encoding="UTF-8" fieldsTerminatedBy="\\t" fieldsEnclosedBy="&quot;" ignoreHeaderLines="1" rowType="http://rs.tdwg.org/dwc/terms/Occurrence">
    <files><location>occurrence.txt</location></files>
    <id/>
    <field term="http://rs.tdwg.org/dwc/terms/taxonKey"/>
    <field term="http://rs.tdwg.org/dwc/terms/scientificName"/>
    <field term="http://rs.tdwg.org/dwc/terms/taxonRank"/>
    <field term="http://rs.tdwg.org/dwc/terms/kingdom"/>
  </core>
</archive>
"""


def test_dwca_taxonomy_accepts_implicit_column_indexes(tmp_path: Path) -> None:
    archive = tmp_path / "gbif-no-index.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("meta.xml", META_WITHOUT_INDEXES)
        z.writestr(
            "occurrence.txt",
            "id\ttaxonKey\tscientificName\ttaxonRank\tkingdom\n1\t2878688\tBellis perennis\tSPECIES\tPlantae\n",
        )
    taxa, names = DwcaTaxonomyImportService._read_archive(archive)
    assert taxa[0]["source_taxon_id"] == "2878688"
    assert taxa[0]["scientific_name"] == "Bellis perennis"
    assert len(names) == 1


def test_dwca_taxonomy_accepts_extracted_folder(tmp_path: Path) -> None:
    folder = tmp_path / "gbif-extracted"
    folder.mkdir()
    (folder / "meta.xml").write_text(META, encoding="utf-8")
    (folder / "occurrence.txt").write_text(
        "id\ttaxonKey\tscientificName\ttaxonRank\tkingdom\n1\t2878688\tBellis perennis\tSPECIES\tPlantae\n",
        encoding="utf-8",
    )
    taxa, names = DwcaTaxonomyImportService._read_archive(folder)
    assert taxa[0]["source_taxon_id"] == "2878688"
    assert len(names) == 1
    assert DwcaTaxonomyImportService._source_checksum(
        folder
    ) == DwcaTaxonomyImportService._source_checksum(folder)


def test_dwca_taxonomy_streams_to_isolated_database(tmp_path: Path) -> None:
    folder = tmp_path / "dwca"
    folder.mkdir()
    (folder / "meta.xml").write_text(META, encoding="utf-8")
    (folder / "occurrence.txt").write_text(
        "id\ttaxonKey\tscientificName\ttaxonRank\tkingdom\n"
        "1\t2878688\tBellis perennis\tSPECIES\tPlantae\n",
        encoding="utf-8",
    )
    result = DwcaTaxonomyImportService().run(folder, workspace=tmp_path / "sources")
    assert result.package_path.name == "gbif.active.sqlite3"
    assert result.package_path.is_file()
    import sqlite3

    connection = sqlite3.connect(result.package_path)
    try:
        assert connection.execute("select count(*) from taxa").fetchone()[0] == 1
        assert (
            connection.execute(
                "select value from source_metadata where key='import_state'"
            ).fetchone()[0]
            == "ready"
        )
    finally:
        connection.close()


def test_taxonomy_working_sets_are_separate_and_filterable(tmp_path: Path) -> None:
    from natureai_next.application.taxonomy_sources import TaxonomySourceLibrary, TaxonomyWorkingSet

    root = tmp_path / "sources"
    root.mkdir()
    import sqlite3

    con = sqlite3.connect(root / "gbif.active.sqlite3")
    con.execute(
        "create table taxa(source_taxon_id text primary key, scientific_name text, authorship text, rank text, status text, parent_source_taxon_id text, accepted_source_taxon_id text, kingdom text, major_group text, taxon_class text, taxon_order text, family text)"
    )
    con.executemany(
        "insert into taxa values(?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "1",
                "Aquila audax",
                None,
                "species",
                "accepted",
                None,
                None,
                "Animalia",
                "Chordata",
                "Aves",
                "Accipitriformes",
                "Accipitridae",
            ),
            (
                "2",
                "Corvus coronoides",
                None,
                "species",
                "accepted",
                None,
                None,
                "Animalia",
                "Chordata",
                "Aves",
                "Passeriformes",
                "Corvidae",
            ),
        ],
    )
    con.commit()
    con.close()
    library = TaxonomySourceLibrary(root)
    assert "Aves" in library.distinct("taxon_class", {"kingdom": "Animalia"})
    item = TaxonomyWorkingSet(
        "Birds of prey", kingdom="Animalia", taxon_class="Aves", taxon_order="Accipitriformes"
    )
    assert library.count(item) == 1
    library.save_set(item)
    assert library.load_sets()[0].name == "Birds of prey"
