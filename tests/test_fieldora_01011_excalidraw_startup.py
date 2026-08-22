import ast
from pathlib import Path


def test_excalidraw_list_item_is_imported_before_startup_use() -> None:
    source_path = (
        Path(__file__).parents[1]
        / "src/natureai_next/ui/qt/science.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    qt_widget_imports = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "PySide6.QtWidgets"
        for alias in node.names
    }
    assert "QListWidgetItem" in qt_widget_imports
    assert "QListWidgetItem(" in source
