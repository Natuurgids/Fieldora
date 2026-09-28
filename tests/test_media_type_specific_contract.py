from natureai_next.server.media_types import canonical_media_type


def test_specific_scientific_media_type_is_not_overridden_by_extension():
    assert canonical_media_type("sample.dat", "application/vnd.vendor.instrument") == "application/vnd.vendor.instrument"
