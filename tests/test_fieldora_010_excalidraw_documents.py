import json
from pathlib import Path

from natureai_next.application.excalidraw_documents import OfflineExcalidrawDocuments


def test_excalidraw_whiteboards_are_documents_with_versions(tmp_path: Path) -> None:
    service = OfflineExcalidrawDocuments(tmp_path / "Documents")
    document = service.create("Field notes")
    assert document == tmp_path / "Documents" / "Whiteboards" / "Field-notes.excalidraw"
    payload = json.loads(document.read_text(encoding="utf-8"))
    assert payload["type"] == "excalidraw"
    assert payload["source"] == "fieldora-offline"
    records = service.list_documents()
    assert records[0].revision_count == 1
    service.snapshot(document)
    assert service.list_documents()[0].revision_count == 2


def test_empty_workspace_creates_and_reuses_drawing_one(tmp_path: Path) -> None:
    service = OfflineExcalidrawDocuments(tmp_path / "Documents")
    document = service.ensure_default_document()
    assert document.name == "Drawing-1.excalidraw"
    assert service.ensure_default_document() == document
    assert len(service.list_documents()) == 1


def test_import_rejects_non_excalidraw_document(tmp_path: Path) -> None:
    source = tmp_path / "not-a-board.json"
    source.write_text('{"type":"other","elements":[]}', encoding="utf-8")
    service = OfflineExcalidrawDocuments(tmp_path / "Documents")
    try:
        service.import_document(source)
    except ValueError as exc:
        assert "not an Excalidraw document" in str(exc)
    else:
        raise AssertionError("invalid document was accepted")


def test_embedded_editor_autosave_preserves_fieldora_identity(tmp_path: Path) -> None:
    service = OfflineExcalidrawDocuments(tmp_path / "Documents")
    document = service.create("Integrated editor")
    original = json.loads(document.read_text(encoding="utf-8"))["fieldora"]
    service.save_payload(
        document,
        json.dumps(
            {
                "type": "excalidraw",
                "version": 2,
                "source": "other",
                "elements": [{"id": "shape-1", "type": "rectangle"}],
                "appState": {"viewBackgroundColor": "#ffffff"},
                "files": {},
            }
        ),
    )
    saved = json.loads(document.read_text(encoding="utf-8"))
    assert saved["source"] == "fieldora-offline"
    assert saved["fieldora"] == original
    assert saved["elements"][0]["id"] == "shape-1"


def test_full_excalidraw_application_is_bundled_and_network_blocked() -> None:
    root = Path(__file__).parents[1]
    application = root / "src/natureai_next/resources/excalidraw"
    index = (application / "index.html").read_text(encoding="utf-8")
    bridge = (root / "src/natureai_next/ui/qt/excalidraw_editor.py").read_text()
    science = (root / "src/natureai_next/ui/qt/science.py").read_text()
    assert "qrc:///qtwebchannel/qwebchannel.js" in index
    assert "connect-src 'none'" in index
    assert len(tuple((application / "assets").glob("*.js"))) > 100
    assert len(tuple((application / "assets/fonts").rglob("*.woff2"))) > 200
    assert "QWebEngineUrlRequestInterceptor" in bridge
    assert '{"file", "qrc", "data", "blob"}' in bridge
    assert "EmbeddedExcalidrawEditor" in science
    assert "Open in Fieldora" in science
    assert "ensure_default_document" in science
    assert "open_document(initial_document)" in science


def test_branding_and_link_alignment_is_fieldora() -> None:
    root = Path(__file__).parents[1]
    splash = (root / "src/natureai_next/ui/qt/startup_splash.py").read_text()
    product = (root / "src/natureai_next/ui/qt/product_pages.py").read_text()
    installer = (root / "scripts/install_windows.ps1").read_text()
    assert '"FIELDORA"' in splash
    assert "Offline biodiversity research & scientific projects" in splash
    assert "fieldora.ico" in splash
    assert 'QPushButton("Fieldora project website")' in product
    assert "SP_DirLinkIcon" in product
    assert product.count("Excalidraw 0.18.1") >= 3
    assert "Name = 'Fieldora'" in installer
