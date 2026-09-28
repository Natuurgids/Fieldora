from natureai_next.server.media_types import canonical_media_type


def test_empty_webview_type_is_recovered_from_filename():
    assert canonical_media_type("observation.jpeg", "") == "image/jpeg"
