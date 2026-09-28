from natureai_next.server.media_types import canonical_media_type


def test_tiff_has_image_media_type():
    assert canonical_media_type("microscopy.tiff", "application/octet-stream") == "image/tiff"
