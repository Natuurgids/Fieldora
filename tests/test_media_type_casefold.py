from natureai_next.server.media_types import canonical_media_type


def test_generic_media_type_comparison_is_case_insensitive():
    assert canonical_media_type("evidence.PDF", " Application/Octet-Stream ") == "application/pdf"
