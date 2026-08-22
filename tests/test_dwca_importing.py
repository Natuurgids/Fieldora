import zipfile
from pathlib import Path

import pytest

from natureai_next.infrastructure.filesystem.importing import (
    DarwinCoreArchiveError,
    DarwinCoreArchiveExpander,
    DirectorySourceScanner,
)

META = """<?xml version="1.0" encoding="UTF-8"?>
<archive xmlns="http://rs.tdwg.org/dwc/text/">
  <core encoding="UTF-8" linesTerminatedBy="\\n" fieldsTerminatedBy="\\t" ignoreHeaderLines="1" rowType="http://rs.tdwg.org/dwc/terms/Occurrence">
    <files><location>occurrence.txt</location></files>
    <id index="0"/>
  </core>
</archive>
"""


def test_scanner_expands_embedded_dwca_media_without_modifying_archive(tmp_path: Path) -> None:
    source = tmp_path / "gbif-source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("meta.xml", META)
        archive.writestr("occurrence.txt", "id\\n1\\n")
        archive.writestr("media/specimen.jpg", b"not-a-decoded-image-yet")
    before = source.read_bytes()

    scanner = DirectorySourceScanner(dwca_expander=DarwinCoreArchiveExpander(tmp_path / "cache"))
    files = scanner.scan((source,), recursive=True)

    assert len(files) == 1
    assert files[0].path.name == "specimen.jpg"
    assert files[0].path.read_bytes() == b"not-a-decoded-image-yet"
    assert source.read_bytes() == before


def test_valid_dwca_without_embedded_media_has_actionable_error(tmp_path: Path) -> None:
    source = tmp_path / "records-only.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("meta.xml", META)
        archive.writestr("occurrence.txt", "id\\n1\\n")

    with pytest.raises(DarwinCoreArchiveError, match="no embedded image files"):
        DarwinCoreArchiveExpander(tmp_path / "cache").expand(source)


def test_unsafe_archive_member_is_not_extracted(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("meta.xml", META)
        archive.writestr("occurrence.txt", "id\\n1\\n")
        archive.writestr("../escape.jpg", b"bad")

    with pytest.raises(DarwinCoreArchiveError, match="no embedded image files"):
        DarwinCoreArchiveExpander(tmp_path / "cache").expand(source)
    assert not (tmp_path / "escape.jpg").exists()


def test_default_library_scanner_ignores_dwca_but_includes_supported_documents(
    tmp_path: Path,
) -> None:
    source = tmp_path / "gbif-source.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("meta.xml", META)
        archive.writestr("occurrence.txt", "id\n1\n")
        archive.writestr("media/specimen.jpg", b"embedded")
    (tmp_path / "notes.txt").write_text("not a photograph", encoding="utf-8")
    photo = tmp_path / "ordinary.jpg"
    photo.write_bytes(b"photo")

    files = DirectorySourceScanner().scan((tmp_path,), recursive=True)

    assert [item.path.name for item in files] == ["notes.txt", "ordinary.jpg"]
