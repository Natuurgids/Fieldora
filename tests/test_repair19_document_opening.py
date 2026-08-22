from pathlib import Path

from natureai_next.domain.importing import ImportSourceKind, classify_import_source


def test_office_and_opendocument_extensions_route_to_documents() -> None:
    extensions = (
        ".doc", ".docm", ".docx", ".odt", ".ods", ".odp",
        ".xls", ".xlsb", ".xlsm", ".xlsx",
        ".ppt", ".pptm", ".pptx", ".pps", ".ppsx", ".pot", ".potx",
        ".rtf", ".csv", ".md", ".txt", ".pdf",
    )
    for extension in extensions:
        assert classify_import_source(Path(f"sample{extension}")) is ImportSourceKind.DOCUMENT


def test_document_viewer_uses_native_and_system_paths() -> None:
    source = (
        Path(__file__).parents[1]
        / "src"
        / "natureai_next"
        / "ui"
        / "qt"
        / "media_library.py"
    ).read_text(encoding="utf-8")
    assert '_NATIVE_TEXT_SUFFIXES = frozenset({".md", ".txt"})' in source
    assert "QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))" in source
    assert "LibreOffice" in source
    assert "Microsoft Office" in source
