from natureai_next.server.media_types import canonical_media_type


def test_geojson_has_specific_media_type():
    assert canonical_media_type("survey.geojson", "application/octet-stream") == "application/geo+json"
