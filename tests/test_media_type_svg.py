from natureai_next.server.media_types import canonical_media_type


def test_svg_has_previewable_media_type():
    assert canonical_media_type("diagram.svg", "application/octet-stream") == "image/svg+xml"
