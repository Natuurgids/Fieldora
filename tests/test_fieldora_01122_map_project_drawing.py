from pathlib import Path
import zipfile

from natureai_next.application.project_management import ProjectExportOptions, ProjectManagementService
from natureai_next.ui.qt.vector_map_view import vector_map_html


def test_vector_map_exposes_direct_project_polygon_workflow(tmp_path: Path) -> None:
    asset_root = Path(__file__).parents[1] / "src" / "natureai_next" / "resources" / "map_renderer"
    html = vector_map_html("area", asset_root, longitude=5.5, latitude=52.7, zoom=11, base_url="http://127.0.0.1/")
    assert "apertureStartProjectDrawing" in html
    assert "apertureFinishProjectDrawing" in html
    assert "aperture-project-polygon:" in html
    assert "aperture-project-drawing" in html


def test_project_snapshot_is_registered_and_exported(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    project_id = service.create_project("Wetland", owner_id="owner", actor_id="owner")
    image = tmp_path / "visible-map.png"
    image.write_bytes(b"PNG test payload")
    snapshot_id = service.add_map_snapshot(
        project_id, "Survey boundary", image, actor_id="owner",
        viewport={"latitude": 52.7, "longitude": 5.8, "zoom": 12},
    )
    assert service.map_snapshots(project_id)[0]["snapshot_id"] == snapshot_id
    destination = tmp_path / "project.zip"
    service.export_research_package(project_id, destination, options=ProjectExportOptions())
    with zipfile.ZipFile(destination) as package:
        names = package.namelist()
        assert "maps/snapshots.json" in names
        assert any(name.startswith("maps/snapshots/") and name.endswith(".png") for name in names)
