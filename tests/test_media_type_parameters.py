from natureai_next.server.media_types import canonical_media_type


def test_generic_type_with_parameters_is_recovered():
    assert canonical_media_type("evidence.pdf", "application/octet-stream; charset=binary") == "application/pdf"
