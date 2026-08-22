from pathlib import Path


def test_excalidraw_file_assets_are_allowed_and_runtime_failure_is_visible() -> None:
    root = Path(__file__).parents[1]
    index = (
        root / "src/natureai_next/resources/excalidraw/index.html"
    ).read_text()
    editor = (
        root / "src/natureai_next/ui/qt/excalidraw_editor.py"
    ).read_text()
    assert "script-src 'self' file: qrc:" in index
    assert "style-src 'self' file:" in index
    assert "'wasm-unsafe-eval'" in index
    assert "javaScriptConsoleMessage" in editor
    assert "document.querySelector('.excalidraw')" in editor
    assert "could not start" in editor
