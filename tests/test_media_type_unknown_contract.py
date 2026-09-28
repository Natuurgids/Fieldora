from natureai_next.server.media_types import canonical_media_type


def test_unknown_extension_remains_generic_when_client_type_is_generic():
    assert canonical_media_type("specimen.fieldora-unknown", "application/octet-stream") == "application/octet-stream"
