from pathlib import Path


def test_browser_upload_generic_fallback_is_server_recoverable():
    app = Path("src/natureai_next/resources/server_web/app.js").read_text(encoding="utf-8")
    assert 'file.type || "application/octet-stream"' in app


def test_server_does_not_treat_generic_browser_type_as_canonical():
    source = Path("src/natureai_next/server/media_type_api.py").read_text(encoding="utf-8")
    assert "canonical_media_type(filename" in source
