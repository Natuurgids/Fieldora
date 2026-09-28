import pytest

from natureai_next.server.media_types import canonical_media_type


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("photo.jpg", "image/jpeg"),
        ("photo.png", "image/png"),
        ("report.pdf", "application/pdf"),
        ("recording.wav", "audio/x-wav"),
        ("recording.mp3", "audio/mpeg"),
        ("clip.mp4", "video/mp4"),
        ("table.csv", "text/csv"),
        ("notes.txt", "text/plain"),
    ],
)
def test_generic_client_type_recovers_gallery_media_type(filename, expected):
    assert canonical_media_type(filename, "application/octet-stream") == expected
