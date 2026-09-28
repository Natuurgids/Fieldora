from natureai_next.server.media_types import canonical_media_type


def test_json_has_application_json_media_type():
    assert canonical_media_type("metadata.json", "application/octet-stream") == "application/json"
