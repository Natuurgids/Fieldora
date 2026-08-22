from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/natureai_next/ui/qt/library.py").read_text(encoding="utf-8")


def test_gallery_thumbnail_reads_are_serial_and_queue_is_bounded() -> None:
    assert "self._thumbnail_limit = 1" in SOURCE
    assert "self._thumbnail_queue_limit = 12" in SOURCE
    assert "available_slots = max(" in SOURCE
    assert "if available_slots <= 0:" in SOURCE


def test_gallery_does_not_prefetch_hundreds_of_thumbnail_files() -> None:
    assert "last_row + 1 + 400" not in SOURCE
    assert "first_row - 400" not in SOURCE
    assert "last_row + 1 + 12" in SOURCE
    assert "first_row - 12" in SOURCE
