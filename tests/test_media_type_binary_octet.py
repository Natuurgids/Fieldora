from natureai_next.server.media_types import canonical_media_type


def test_legacy_binary_octet_stream_is_recovered():
    assert canonical_media_type("observation.png", "binary/octet-stream") == "image/png"
