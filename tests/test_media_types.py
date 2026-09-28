from natureai_next.server.media_types import canonical_media_type


def test_generic_browser_types_are_inferred_from_filename():
    assert canonical_media_type("field-photo.JPG", "") == "image/jpeg"
    assert canonical_media_type("field-photo.jpg", "application/octet-stream") == "image/jpeg"
    assert canonical_media_type("evidence.pdf", "binary/octet-stream") == "application/pdf"
    assert canonical_media_type("observations.csv", "application/octet-stream") == "text/csv"
    assert canonical_media_type("track.gpx", "application/octet-stream") != "application/octet-stream"


def test_specific_declared_type_is_preserved():
    assert canonical_media_type("opaque.bin", "image/tiff; charset=binary") == "image/tiff"


def test_unknown_type_remains_safe_generic_binary():
    assert canonical_media_type("sample.fieldora-unknown", "") == "application/octet-stream"
