from pathlib import Path


def test_full_backbone_option_is_separate_from_occurrence_corpus():
    source = Path("src/natureai_next/ui/qt/settings_pages.py").read_text(encoding="utf-8")
    assert "Download complete GBIF Backbone Taxonomy" in source
    assert "gbif-backbone-download-import" in source
    assert "multi-terabyte" in source
    assert "backbone/current/backbone.zip" in source


def test_large_downloader_supports_progress_resume_and_cancellation():
    source = Path("src/natureai_next/application/ai_setup.py").read_text(encoding="utf-8")
    assert 'headers["Range"] = f"bytes={offset}-"' in source
    assert "progress: Callable" in source
    assert "cancelled: Callable" in source
    assert ".part" in source
    assert "MiB received" in source


def test_bioclip_setup_names_full_supported_model_and_not_92tb_corpus():
    source = Path("src/natureai_next/ui/qt/ai_setup.py").read_text(encoding="utf-8")
    assert "Download complete supported BioCLIP model" in source
    assert "not the 92 TB corpus" in source
    assert "Cancel download" in source


def test_bioclip_download_retries_quickly_and_keeps_resume_file():
    source = Path("src/natureai_next/application/ai_setup.py").read_text(encoding="utf-8")
    assert "delays = (0, 1, 2, 4, 8, 10)" in source
    assert "8 * 1024 * 1024" in source
    assert "partial file was kept for resume" in source
