import json
import ast
from pathlib import Path


def test_release_is_fieldora_00834() -> None:
    release = json.loads(Path("PLATFORM_RELEASE.json").read_text(encoding="utf-8"))
    package = Path("src/natureai_next/__init__.py").read_text(encoding="utf-8")
    assert release["product"] == "Fieldora"
    assert release["version"] == "5.4.0"
    assert release["library_migration_required"] is False
    assert '__version__ = "5.4.0"' in package


def test_science_workspace_is_connected_to_navigation_and_storage() -> None:
    application = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    science = Path("src/natureai_next/ui/qt/science.py").read_text(encoding="utf-8")
    assert '"Science Projects"' in application
    assert '"Science Dossiers"' in application
    assert '"Science Whiteboard"' in application
    assert '("Whiteboards", "Science Whiteboard")' in application
    assert "ScienceWorkspace(" in application
    assert "science.sqlite3" in application
    assert "New Project" in science
    assert "New Excalidraw document" in science
    assert "Create document version" in science
    assert "Add Activity" in science
    assert "science_artifacts" in science
    assert "Plants & Fungi" in science
    assert "science_dossiers" in science
    assert "science_dossier_media" in science
    assert "Create Dossier" in science
    assert "PRAGMA busy_timeout=5000" in science
    assert "science_project_stages" in science
    assert "science_project_resources" in science
    assert "science_project_budgets" in science
    assert "science_board_shapes" in science
    assert "science_whiteboards" in science
    assert "science_whiteboard_elements" in science
    assert "science_dossier_whiteboards" in science
    assert "EmbeddedExcalidrawEditor" in science
    assert "Export Project Package" in science
    assert "Import Project Package" in science


def test_science_workspace_imports_every_qt_layout_it_constructs() -> None:
    source = Path("src/natureai_next/ui/qt/science.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "PySide6.QtWidgets"
        for alias in node.names
    }
    assert "QFormLayout" in imported
