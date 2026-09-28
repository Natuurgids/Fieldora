from pathlib import Path


def test_staged_ingestion_retains_signature_detection_and_filename_fallback():
    source = Path("src/natureai_next/server/staged_ingestion.py").read_text(encoding="utf-8")
    assert "mimetypes.guess_type" in source
    assert "application/pdf" in source
    assert "image/jpeg" in source
    assert "image/png" in source
