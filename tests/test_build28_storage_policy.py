from pathlib import Path

from natureai_next.domain.importing import ImportStoragePolicy


def test_original_storage_policies_are_explicit_and_stable():
    assert ImportStoragePolicy.MANAGED.value == "managed"
    assert ImportStoragePolicy.REFERENCED.value == "referenced"
    assert ImportStoragePolicy.HYBRID.value == "hybrid"


def test_import_ui_exposes_source_and_aperture_original_choices():
    text = Path("src/natureai_next/ui/qt/importing.py").read_text(encoding="utf-8")
    assert "Create an Aperture original (managed)" in text
    assert "Leave in current location (Linked)" in text
    assert "import/default_storage_policy" in text

def test_inspector_distinguishes_source_and_managed_master():
    text = Path("src/natureai_next/ui/qt/library.py").read_text(encoding="utf-8")
    assert "Source file:" in text
    assert "Aperture original:" in text
