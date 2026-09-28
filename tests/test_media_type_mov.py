from natureai_next.server.media_types import canonical_media_type


def test_mov_has_quicktime_media_type():
    assert canonical_media_type("camera.mov", "application/octet-stream") == "video/quicktime"
