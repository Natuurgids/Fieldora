from natureai_next.application.map_workspace import MapWorkspaceResult
from natureai_next.domain.spatial_intelligence import SpatialAssetCluster
from natureai_next.ui.qt.vector_map_view import vector_overlay_data


def test_vector_overlay_uses_numbered_media_clusters():
    cluster = SpatialAssetCluster(42.7,23.3,128,96,14,18,103,21,4,"province","Sofia")
    result = type("R",(),{"observations":(),"asset_clusters":(cluster,),"sites":()})()
    feature = vector_overlay_data(result)["aperture-assets"]["features"][0]
    assert feature["properties"]["count"] == 128
    assert feature["properties"]["image_count"] == 96
    assert feature["properties"]["audio_count"] == 18
    assert feature["properties"]["level"] == "province"


def test_repair23_migration_and_shared_renderers_are_present():
    from pathlib import Path
    root=Path(__file__).parents[1]
    migration=(root/"src/natureai_next/infrastructure/database/migrations/v026_spatial_asset_hierarchy.py").read_text()
    raster=(root/"src/natureai_next/ui/qt/maps.py").read_text()
    vector=(root/"src/natureai_next/ui/qt/vector_map_view.py").read_text()
    assert "ix_locations_admin_hierarchy" in migration
    assert "result.asset_clusters" in raster
    assert "aperture-media-counts" in vector
