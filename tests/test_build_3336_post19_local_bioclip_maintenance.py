from pathlib import Path


def test_local_bioclip_folder_is_supported_by_setup_request():
    source = Path("src/natureai_next/application/ai_setup.py").read_text(encoding="utf-8")
    assert "model_folder: Path | None = None" in source
    assert "folder.rglob(BIOCLIP_CHECKPOINT_FILENAME)" in source
    assert "Validated the local BioCLIP model folder" in source


def test_setup_dialog_exposes_complete_folder_import():
    source = Path("src/natureai_next/ui/qt/ai_setup.py").read_text(encoding="utf-8")
    assert "Complete BioCLIP folder" in source
    assert "Import and activate local BioCLIP" in source
    assert "model_folder=Path(model_folder_text)" in source


def test_maintenance_center_exposes_bioclip_setup_and_scrolls():
    source = Path("src/natureai_next/ui/qt/maintenance_center.py").read_text(encoding="utf-8")
    assert "Download or Import BioCLIP" in source
    assert "def manage_bioclip_resources" in source
    assert "QScrollArea" in source
    assert "scroll.setWidgetResizable(True)" in source
