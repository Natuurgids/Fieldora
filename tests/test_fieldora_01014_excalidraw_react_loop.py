from pathlib import Path


def test_excalidraw_save_debounce_does_not_use_react_state() -> None:
    root = Path(__file__).parents[1]
    wrapper = (root / "web/excalidraw/src/main.jsx").read_text()
    assert "saveTimerRef = useRef(null)" in wrapper
    assert "bridgeRef = useRef(null)" in wrapper
    assert "const [timer, setTimer]" not in wrapper
    assert "const save = useCallback(" in wrapper
    assert "}, []);" in wrapper


def test_excalidraw_source_csp_supports_packaged_file_assets() -> None:
    root = Path(__file__).parents[1]
    source_index = (root / "web/excalidraw/index.html").read_text()
    assert "script-src 'self' file: qrc:" in source_index
    assert "style-src 'self' file:" in source_index
    assert "connect-src 'none'" in source_index
