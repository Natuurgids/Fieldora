from pathlib import Path

import pytest

from natureai_next.application.import_service import _obvious_unsupported_format
from natureai_next.domain.importing import ImportSourceKind, classify_import_source


@pytest.mark.parametrize(
    "suffix",
    [".docx", ".docm", ".xlsx", ".xlsm", ".xlsb", ".pptx", ".pptm", ".ppsx", ".potx", ".odt", ".ods", ".odp"],
)
def test_zip_based_documents_are_not_rejected_as_archives(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / f"document{suffix}"
    source.write_bytes(b"PK\x03\x04placeholder")

    assert classify_import_source(source) is ImportSourceKind.DOCUMENT
    assert _obvious_unsupported_format(source) is None


def test_unknown_zip_container_remains_rejected(tmp_path: Path) -> None:
    source = tmp_path / "archive.zip"
    source.write_bytes(b"PK\x03\x04placeholder")

    assert classify_import_source(source) is ImportSourceKind.UNKNOWN
    assert _obvious_unsupported_format(source) == "ZIP archives are not importable media"
