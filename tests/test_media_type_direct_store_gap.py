from pathlib import Path


def test_installed_runtime_normalizes_before_governed_store_boundary():
    composition = Path("src/natureai_next/server/offline_first_api.py").read_text(encoding="utf-8")
    api = Path("src/natureai_next/server/media_type_api.py").read_text(encoding="utf-8")
    assert "CanonicalMediaTypeApiMixin" in composition
    assert "canonical_media_type" in api
