from natureai_next.domain.spatial_intelligence import SpatialAsset
from natureai_next.application.map_workspace import asset_location_label, cardinal_coordinate
from natureai_next.ui.qt.vector_map_view import vector_overlay_data


def testcardinal_coordinate_preserves_all_hemispheres() -> None:
    assert cardinal_coordinate(51.5, latitude=True).endswith("N")
    assert cardinal_coordinate(-33.9, latitude=True).endswith("S")
    assert cardinal_coordinate(4.9, latitude=False).endswith("E")
    assert cardinal_coordinate(-122.4, latitude=False).endswith("W")


def test_asset_locations_keep_capture_and_subject_roles() -> None:
    capture = SpatialAsset("asset-1", 51.5, 4.9, None, "capture")
    subject = SpatialAsset("asset-1", -33.9, -122.4, None, "subject")
    assert "Capture location" in asset_location_label(capture)
    assert "51.500000° N" in asset_location_label(capture)
    assert "Subject location" in asset_location_label(subject)
    assert "33.900000° S" in asset_location_label(subject)

    result = type("Result", (), {"observations": (), "assets": (capture, subject), "sites": ()})()
    collections = vector_overlay_data(result)
    features = collections["aperture-assets"]["features"]
    assert [feature["properties"]["role"] for feature in features] == ["capture", "subject"]
