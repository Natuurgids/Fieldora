from pathlib import Path

from PIL import Image

from natureai_next.infrastructure.imaging.pillow_adapter import PillowImageDecoder
from natureai_next.ports.media import RenderRequest


def test_thumbnail_render_flushes_through_writable_handle(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.jpg"
    destination = tmp_path / "thumb.jpg"
    Image.new("RGB", (120, 80), "white").save(source, format="JPEG")

    import natureai_next.infrastructure.imaging.pillow_adapter as adapter

    original_fsync = adapter.os.fsync

    def windows_like_fsync(fd: int) -> None:
        # A writable descriptor is required by Windows FlushFileBuffers.
        import os
        os.write(fd, b"")
        original_fsync(fd)

    monkeypatch.setattr(adapter.os, "fsync", windows_like_fsync)
    result = PillowImageDecoder().render(
        RenderRequest(source, destination, 64, 64, 85, "JPEG")
    )

    assert destination.is_file()
    assert result.pixel_width <= 64
    assert result.pixel_height <= 64
