from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from natureai_next.application.map_workspace import OfflineMapWorkspaceService
from natureai_next.domain.export_packages import (
    ExportPackageAttachment,
    ExportPackageOriginal,
    ExportPackagePlan,
    MissingOriginalPolicy,
)
from natureai_next.infrastructure.exporting.packages import LocalExportPackageBuilder


def test_export_package_includes_report_and_available_original_and_reports_missing(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.pdf"
    report.write_bytes(b"report")
    photo = tmp_path / "photo.raw"
    photo.write_bytes(b"photo")
    missing = tmp_path / "missing.wav"
    result = LocalExportPackageBuilder().build(
        ExportPackagePlan(
            public_id="package-1",
            destination_directory=tmp_path / "out",
            attachments=(ExportPackageAttachment(report, "report/report.pdf", "report"),),
            originals=(
                ExportPackageOriginal(
                    "photo-1",
                    "photo",
                    photo,
                    "media/photos/photo.raw",
                    photo.stat().st_size,
                    hashlib.sha256(b"photo").hexdigest(),
                ),
                ExportPackageOriginal("sound-1", "sound", missing, "media/sounds/missing.wav"),
            ),
        )
    )
    assert result.included_count == 2
    assert result.unavailable_count == 1
    manifest = json.loads(result.manifest_path.read_text())
    assert {item["state"] for item in manifest["items"]} == {"included", "missing"}
    assert (result.destination_directory / "media/photos/photo.raw").read_bytes() == b"photo"


def test_export_package_require_all_is_atomic(tmp_path: Path) -> None:
    report = tmp_path / "report.pdf"
    report.write_bytes(b"report")
    destination = tmp_path / "out"
    try:
        LocalExportPackageBuilder().build(
            ExportPackagePlan(
                public_id="package-2",
                destination_directory=destination,
                attachments=(ExportPackageAttachment(report, "report/report.pdf", "report"),),
                originals=(
                    ExportPackageOriginal(
                        "photo-1", "photo", tmp_path / "missing.raw", "media/photos/missing.raw"
                    ),
                ),
                missing_original_policy=MissingOriginalPolicy.REQUIRE_ALL,
            )
        )
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("strict export should fail")
    assert not destination.exists()


def test_map_service_resolves_tile_from_adjacent_package() -> None:
    class Package:
        def __init__(self, public_id, west, east):
            self.public_id = public_id
            self.west = west
            self.east = east
            self.south = -90
            self.north = 90

    left = Package("left", -20, 0)
    right = Package("right", 0, 20)

    class Maps:
        def tile(self, public_id, zoom, x, y):
            return f"{public_id}:{x}:{y}" if public_id == "right" else None

    service = object.__new__(OfflineMapWorkspaceService)
    service._maps = Maps()
    package, tile = service.tile_for_coordinate(
        (left, right), latitude=0, longitude=10, zoom=4, x=8, y=8
    )
    assert package is right
    assert tile == "right:8:8"


def test_reporting_workspace_is_visible_and_export_package_copy_is_parallel():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    application = (root / "src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    reporting = (root / "src/natureai_next/ui/qt/reporting.py").read_text(encoding="utf-8")
    packages = (root / "src/natureai_next/infrastructure/exporting/packages.py").read_text(
        encoding="utf-8"
    )
    activity = (root / "src/natureai_next/ui/qt/activity.py").read_text(encoding="utf-8")

    assert '"Export": ("Export",)' in application
    assert '"Reporting": ("Reporting",)' in application
    assert "Export…" in application
    assert "Reporting…" in application
    assert "Export portable package…" in reporting
    assert "Export JSON…" in reporting
    assert "Generate summary report…" in reporting
    assert "ThreadPoolExecutor" in packages
    assert 'thread_name_prefix="aperture-export"' in packages
    assert '"export.package"' in activity
    assert '"report.generate"' in activity


def test_map_workspace_can_filter_to_one_selected_area() -> None:
    from natureai_next.domain.maps import OfflineMapPackage

    def pkg(public_id: str, west: float, east: float) -> OfflineMapPackage:
        return OfflineMapPackage(
            public_id=public_id,
            provider_key="test",
            package_name=public_id,
            package_version="1",
            format="mbtiles",
            package_path=f"/{public_id}.mbtiles",
            installed_at_us=1,
            min_zoom=0,
            max_zoom=18,
            west=west,
            south=-10,
            east=east,
            north=10,
        )

    left, right = pkg("left", -20, 0), pkg("right", 0, 20)

    class Maps:
        def capabilities(self):
            from natureai_next.domain.maps import MapPackageCapability

            return tuple(
                MapPackageCapability(
                    p.public_id, p.package_name, p.format, True, "raster", "ready", "", 18
                )
                for p in (left, right)
            )

        def list_all(self):
            return (left, right)

        def covering(self, latitude, longitude):
            return (left, right)

        def tile(self, public_id, zoom, x, y):
            return None

    class Spatial:
        def observations_in_bounds(self, bounds):
            return ()

        def assets_in_bounds(self, bounds):
            return ()

        def list_sites_in_bounds(self, bounds):
            return ()

    service = OfflineMapWorkspaceService(maps=Maps(), spatial=Spatial())
    result = service.workspace(latitude=0, longitude=0, zoom=4, package_ids=frozenset({"right"}))
    assert [p.public_id for p in result.packages] == ["right"]


def test_all_area_selector_and_combined_viewpoint_are_present() -> None:
    from pathlib import Path

    from natureai_next.application.map_workspace import packages_viewpoint
    from natureai_next.domain.maps import OfflineMapPackage

    package_a = OfflineMapPackage(
        "a", "test", "A", "1", "mbtiles", "/a", 1, west=-10, south=50, east=0, north=55
    )
    package_b = OfflineMapPackage(
        "b", "test", "B", "1", "mbtiles", "/b", 1, west=0, south=50, east=10, north=55
    )
    viewpoint = packages_viewpoint((package_a, package_b))
    assert -1 <= viewpoint.longitude <= 1
    assert 50 <= viewpoint.latitude <= 55
    ui = (Path(__file__).resolve().parents[1] / "src/natureai_next/ui/qt/maps.py").read_text(
        encoding="utf-8"
    )
    assert 'self._areas.addItem("All", "__all__")' in ui
    assert "package_ids=package_ids" in ui


def test_all_mode_uses_composite_vector_packages():
    ui = (
        Path(__file__).resolve().parents[1] / "src" / "natureai_next" / "ui" / "qt" / "maps.py"
    ).read_text(encoding="utf-8")
    assert "vector_packages = (" in ui
    assert 'if selected_id == "__all__"' in ui
    assert "vector_source = (" in ui
    assert "combined_sources = vector_packages + nautical_overlays" in ui


def test_nautical_overlay_remains_enabled_with_selected_basemap() -> None:
    from natureai_next.domain.maps import OfflineMapPackage

    base = OfflineMapPackage(
        "base", "test", "Base", "1", "mbtiles", "/base", 1,
        min_zoom=0, max_zoom=18, west=-20, south=-10, east=20, north=10,
    )
    overlay = OfflineMapPackage(
        "sea", "openseamap.seamark.mbtiles", "OpenSeaMap", "1", "mbtiles", "/sea", 1,
        min_zoom=0, max_zoom=18, west=-20, south=-10, east=20, north=10,
        provider_metadata_json='{"map_role":"nautical-overlay"}',
    )

    class Maps:
        def capabilities(self):
            from natureai_next.domain.maps import MapPackageCapability
            return tuple(
                MapPackageCapability(p.public_id, p.package_name, p.format, True, "raster", "ready", "")
                for p in (base, overlay)
            )

        def list_all(self):
            return base, overlay

        def covering(self, latitude, longitude):
            return base, overlay

        def tile(self, public_id, zoom, x, y):
            return f"{public_id}:{zoom}:{x}:{y}"

    class Spatial:
        def observations_in_bounds(self, bounds):
            return ()

        def assets_in_bounds(self, bounds):
            return ()

        def list_sites_in_bounds(self, bounds):
            return ()

    service = OfflineMapWorkspaceService(maps=Maps(), spatial=Spatial())
    result = service.workspace(
        latitude=0, longitude=0, zoom=4, package_ids=frozenset({"base"})
    )
    assert [item.public_id for item in result.packages] == ["base", "sea"]
    assert service.tile_for_coordinate(
        result.packages, latitude=0, longitude=0, zoom=4, x=8, y=8
    )[0] is base
    assert service.overlay_tiles_for_coordinate(
        result.packages, latitude=0, longitude=0, zoom=4, x=8, y=8
    ) == ((overlay, "sea:4:8:8"),)


def test_openseamap_import_validates_and_declares_overlay_role(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from natureai_next.application.map_acquisition import OfflineMapAcquisitionService

    source = tmp_path / "seamarks.mbtiles"
    connection = sqlite3.connect(source)
    connection.executescript(
        """
        CREATE TABLE metadata (name TEXT, value TEXT);
        CREATE TABLE tiles (
            zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB
        );
        """
    )
    connection.executemany(
        "INSERT INTO metadata VALUES(?,?)",
        (
            ("name", "OpenSeaMap Test Region"),
            ("format", "png"),
            ("bounds", "-5,50,5,55"),
            ("minzoom", "0"),
            ("maxzoom", "12"),
        ),
    )
    connection.execute("INSERT INTO tiles VALUES(0,0,0,?)", (b"\x89PNG\r\n\x1a\n",))
    connection.commit()
    connection.close()

    class Catalog:
        def __init__(self):
            self.values = {}

        def get(self, public_id):
            return self.values[public_id]

        def register(self, package):
            self.values[package.public_id] = package

        def remove(self, public_id):
            self.values.pop(public_id, None)

    class Packages:
        def __init__(self, catalog):
            self.catalog = catalog

        def verify(self, public_id):
            package = self.catalog.get(public_id)
            return SimpleNamespace(valid=Path(package.package_path).is_file(), message="valid")

        def enable(self, public_id):
            return None

    catalog = Catalog()
    service = OfflineMapAcquisitionService(
        catalog, Packages(catalog), tmp_path / "installed"
    )
    result = service.import_openseamap_mbtiles(source)
    package = catalog.get(result.package_public_id)
    metadata = json.loads(package.provider_metadata_json)
    assert package.provider_key == "openseamap.seamark.mbtiles"
    assert package.attribution_url == "https://www.openseamap.org/"
    assert metadata["map_role"] == "nautical-overlay"
    assert metadata["navigation_status"] == "reference-only"


def test_vector_server_merges_same_named_layers_from_adjacent_packages():
    from natureai_next.ui.qt.vector_map_server import _encode_field, _fields, _merge_vector_tiles

    def feature(feature_id: int) -> bytes:
        return (
            _encode_field(1, 0, feature_id)
            + _encode_field(3, 0, 1)
            + _encode_field(4, 2, b"\x09\x00\x00")
        )

    def tile(feature_id: int) -> bytes:
        layer = (
            _encode_field(15, 0, 2)
            + _encode_field(1, 2, b"transportation")
            + _encode_field(2, 2, feature(feature_id))
            + _encode_field(5, 0, 4096)
        )
        return _encode_field(3, 2, layer)

    merged = _merge_vector_tiles([tile(10), tile(20)])
    layers = [bytes(value) for number, wire, value in _fields(merged) if number == 3 and wire == 2]
    assert len(layers) == 1
    features = [
        bytes(value) for number, wire, value in _fields(layers[0]) if number == 2 and wire == 2
    ]
    ids = [
        next(value for number, wire, value in _fields(item) if number == 1 and wire == 0)
        for item in features
    ]
    assert ids == [10, 20]


def test_composite_regional_packages_keep_declared_zoom_range():
    from natureai_next.application.map_workspace import package_effective_min_zoom
    from natureai_next.domain.maps import OfflineMapPackage

    province = OfflineMapPackage(
        "groningen",
        "geofabrik",
        "Groningen",
        "1",
        "vector-mbtiles",
        "/g.mbtiles",
        1,
        min_zoom=0,
        max_zoom=14,
        west=6.1,
        south=53.0,
        east=7.3,
        north=53.6,
    )
    assert package_effective_min_zoom(province, composite=True) == 0
    assert package_effective_min_zoom(province, composite=False) == 0


def test_vector_tile_coverage_uses_tile_intersection_not_center():
    from types import SimpleNamespace

    from natureai_next.ui.qt.vector_map_server import _package_covers_tile

    package = SimpleNamespace(min_zoom=0, max_zoom=14, west=3.2, south=50.7, east=7.3, north=53.7)
    assert _package_covers_tile(package, 7, 65, 41, composite=True)
