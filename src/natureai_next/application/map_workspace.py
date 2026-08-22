"""Application service for the first offline map workspace."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from natureai_next.application.knowledge_engine import KnowledgeEngine
from natureai_next.domain.maps import (
    MapPackageCapability,
    OfflineMapPackage,
    OfflineRasterTile,
    is_nautical_overlay,
)
from natureai_next.domain.spatial_intelligence import (
    GeoBounds,
    MonitoringSiteSummary,
    SpatialAsset,
    SpatialAssetCluster,
    SpatialObservation,
)
from natureai_next.ports.map_workspace import OfflineMapQuery, SpatialMapQuery


def cardinal_coordinate(value: float, *, latitude: bool) -> str:
    """Format signed coordinates with their N/S/E/W hemisphere."""
    positive = "N" if latitude else "E"
    negative = "S" if latitude else "W"
    hemisphere = negative if value < 0 else positive
    return f"{abs(value):.6f}° {hemisphere}"


def asset_location_label(asset) -> str:
    role = {"capture": "Capture location", "subject": "Subject location", "user_defined": "User-defined location"}.get(asset.location_role, "Location")
    latitude = cardinal_coordinate(asset.latitude, latitude=True)
    longitude = cardinal_coordinate(asset.longitude, latitude=False)
    return f"{role} · {latitude}, {longitude} · Image {asset.asset_public_id}"


@dataclass(frozen=True, slots=True)
class MapWorkspaceResult:
    package: OfflineMapPackage | None
    packages: tuple[OfflineMapPackage, ...]
    bounds: GeoBounds
    observations: tuple[SpatialObservation, ...]
    assets: tuple[SpatialAsset, ...]
    asset_clusters: tuple[SpatialAssetCluster, ...]
    sites: tuple[MonitoringSiteSummary, ...]
    attribution: str
    attribution_url: str


class OfflineMapWorkspaceService:
    """Combines optional map packages with core-library spatial records."""

    def __init__(
        self,
        *,
        maps: OfflineMapQuery,
        spatial: SpatialMapQuery,
        knowledge_engine: KnowledgeEngine | None = None,
    ) -> None:
        self._maps = maps
        self._spatial = spatial
        self._knowledge_engine = knowledge_engine

    def workspace(
        self,
        *,
        latitude: float,
        longitude: float,
        zoom: int,
        package_ids: frozenset[str] | None = None,
    ) -> MapWorkspaceResult:
        zoom = max(0, min(22, int(zoom)))
        bounds = viewport_bounds(latitude, longitude, zoom, tile_radius=2)
        composite = package_ids is None
        eligible = tuple(
            package
            for package in self.available_packages()
            if (
                package_ids is None
                or package.public_id in package_ids
                or is_nautical_overlay(package)
            )
            and package.format == "mbtiles"
            and zoom >= package_effective_min_zoom(package, composite=composite)
            and (package.max_zoom is None or zoom <= package.max_zoom)
        )
        covering_ids = {package.public_id for package in self._maps.covering(latitude, longitude)}
        packages = tuple(
            sorted(
                eligible,
                key=lambda item: (item.public_id not in covering_ids, item.package_name.casefold()),
            )
        )
        package = next(
            (
                item
                for item in packages
                if item.public_id in covering_ids and not is_nautical_overlay(item)
            ),
            None,
        )
        assets = self._spatial.assets_in_bounds(bounds)
        cluster_query = getattr(self._spatial, "asset_clusters_in_bounds", None)
        asset_clusters = (
            cluster_query(bounds, zoom=zoom)
            if cluster_query is not None
            else tuple(
                SpatialAssetCluster(
                    item.latitude, item.longitude, 1,
                    1 if item.media_type == "image" else 0,
                    1 if item.media_type == "video" else 0,
                    1 if item.media_type == "audio" else 0,
                    1 if item.location_role == "capture" else 0,
                    1 if item.location_role == "subject" else 0,
                    1 if item.location_role == "user_defined" else 0,
                    "location", asset_location_label(item),
                )
                for item in assets
            )
        )
        return MapWorkspaceResult(
            package=package,
            packages=packages,
            bounds=bounds,
            observations=(
                self._knowledge_engine.observations_in_area(bounds)
                if self._knowledge_engine is not None
                else self._spatial.observations_in_bounds(bounds)
            ),
            assets=assets,
            asset_clusters=asset_clusters,
            sites=self._spatial.list_sites_in_bounds(bounds),
            attribution="" if package is None else package.attribution,
            attribution_url="" if package is None else package.attribution_url,
        )

    def tile_for_coordinate(
        self,
        packages: tuple[OfflineMapPackage, ...],
        *,
        latitude: float,
        longitude: float,
        zoom: int,
        x: int,
        y: int,
    ) -> tuple[OfflineMapPackage | None, OfflineRasterTile | None]:
        """Resolve one visible tile against all eligible adjacent packages.

        Package selection is geographic rather than tied to the package that
        covered the original viewport centre. This keeps existing single-map
        behaviour while allowing neighbouring files to form one canvas.
        """
        for package in packages:
            if is_nautical_overlay(package):
                continue
            if not _package_covers(package, latitude=latitude, longitude=longitude):
                continue
            tile = self._maps.tile(package.public_id, zoom, x, y)
            if tile is not None:
                return package, tile
        return None, None

    def overlay_tiles_for_coordinate(
        self,
        packages: tuple[OfflineMapPackage, ...],
        *,
        latitude: float,
        longitude: float,
        zoom: int,
        x: int,
        y: int,
    ) -> tuple[tuple[OfflineMapPackage, OfflineRasterTile], ...]:
        overlays = []
        for package in packages:
            if not is_nautical_overlay(package) or not _package_covers(
                package, latitude=latitude, longitude=longitude
            ):
                continue
            tile = self._maps.tile(package.public_id, zoom, x, y)
            if tile is not None:
                overlays.append((package, tile))
        return tuple(overlays)

    def available_packages(self) -> tuple[OfflineMapPackage, ...]:
        """Return enabled packages with a currently available renderer."""
        renderable = {
            item.package_public_id for item in self._maps.capabilities() if item.renderable
        }
        return tuple(
            package
            for package in self._maps.list_all()
            if package.enabled and package.status == "installed" and package.public_id in renderable
        )

    def package_capabilities(self) -> tuple[MapPackageCapability, ...]:
        """Report package/renderer readiness without attempting tile decoding."""
        return self._maps.capabilities()

    def package(self, public_id: str) -> OfflineMapPackage:
        package = self._maps.get(public_id)
        if package not in self.available_packages():
            raise ValueError("offline map package is not enabled and displayable")
        return package

    def tile(self, package_public_id: str, zoom: int, x: int, y: int) -> OfflineRasterTile | None:
        return self._maps.tile(package_public_id, zoom, x, y)


def package_extent_area(package: OfflineMapPackage) -> float | None:
    """Return approximate geographic envelope area in square degrees."""
    if None in (package.west, package.south, package.east, package.north):
        return None
    west, east = float(package.west), float(package.east)
    width = east - west if east >= west else 360.0 - west + east
    height = max(0.0, float(package.north) - float(package.south))
    return max(0.0, width) * height


def package_is_overview(package: OfflineMapPackage) -> bool:
    """Identify country/world packages suitable for low-zoom composition.

    Regional Geofabrik extracts contain buffered low-zoom tiles outside their
    administrative footprint. They must not be treated as country overview
    sources merely because those tiles exist in MBTiles.
    """
    name = str(
        getattr(package, "package_name", Path(str(getattr(package, "package_path", ""))).stem)
    ).casefold()
    provider = str(getattr(package, "provider_key", "")).casefold()
    overview_tokens = (
        "netherlands",
        "nederland",
        "europe",
        "world",
        "global",
        "country",
        "overview",
    )
    if any(token in name for token in overview_tokens):
        return True
    area = package_extent_area(package)
    return area is None or area >= 12.0 or "overview" in provider


def package_effective_min_zoom(package: OfflineMapPackage, *, composite: bool) -> int:
    """Use the package's declared zoom range in both selected and composite modes."""
    return 0 if package.min_zoom is None else int(package.min_zoom)


@dataclass(frozen=True, slots=True)
class MapPackageViewpoint:
    latitude: float
    longitude: float
    zoom: int


def package_viewpoint(package: OfflineMapPackage) -> MapPackageViewpoint:
    """Return a practical initial viewport for one bounded offline package."""
    if None in (package.west, package.south, package.east, package.north):
        raise ValueError("the installed package has no geographic bounds")
    west, south = float(package.west), float(package.south)
    east, north = float(package.east), float(package.north)
    longitude = (
        (west + east) / 2.0
        if east >= west
        else ((west + east + 360.0) / 2.0 + 180.0) % 360.0 - 180.0
    )
    latitude = (south + north) / 2.0
    minimum = 0 if package.min_zoom is None else int(package.min_zoom)
    maximum = 18 if package.max_zoom is None else int(package.max_zoom)
    chosen = minimum
    for zoom in range(minimum, maximum + 1):
        width = abs(lon_to_tile_x(east, zoom) - lon_to_tile_x(west, zoom))
        height = abs(lat_to_tile_y(south, zoom) - lat_to_tile_y(north, zoom))
        if width <= 2.5 and height <= 2.5:
            chosen = zoom
        else:
            break
    return MapPackageViewpoint(
        latitude=max(-85.0, min(85.0, latitude)),
        longitude=longitude,
        zoom=chosen,
    )


def packages_viewpoint(packages: tuple[OfflineMapPackage, ...]) -> MapPackageViewpoint:
    """Return one practical viewport covering all bounded packages.

    The calculation intentionally ignores unbounded packages. At world scale the
    resulting zoom is limited by package resolution during normal tile selection.
    """
    bounded = tuple(
        package
        for package in packages
        if None not in (package.west, package.south, package.east, package.north)
    )
    if not bounded:
        return MapPackageViewpoint(latitude=0.0, longitude=0.0, zoom=2)
    south = min(float(package.south) for package in bounded)
    north = max(float(package.north) for package in bounded)
    # Dateline-spanning catalogues are safest when shown from the world centre.
    if any(float(package.west) > float(package.east) for package in bounded):
        west, east = -180.0, 180.0
    else:
        west = min(float(package.west) for package in bounded)
        east = max(float(package.east) for package in bounded)
    latitude = (south + north) / 2.0
    longitude = (west + east) / 2.0
    chosen = 0
    for zoom in range(0, 19):
        width = abs(lon_to_tile_x(east, zoom) - lon_to_tile_x(west, zoom))
        height = abs(lat_to_tile_y(south, zoom) - lat_to_tile_y(north, zoom))
        if width <= 2.5 and height <= 2.5:
            chosen = zoom
        else:
            break
    return MapPackageViewpoint(
        latitude=max(-85.0, min(85.0, latitude)),
        longitude=((longitude + 180.0) % 360.0) - 180.0,
        zoom=chosen,
    )


def lon_to_tile_x(longitude: float, zoom: int) -> float:
    return (longitude + 180.0) / 360.0 * (1 << zoom)


def lat_to_tile_y(latitude: float, zoom: int) -> float:
    latitude = max(-85.05112878, min(85.05112878, latitude))
    radians = math.radians(latitude)
    return (1.0 - math.asinh(math.tan(radians)) / math.pi) / 2.0 * (1 << zoom)


def tile_x_to_lon(x: float, zoom: int) -> float:
    return x / (1 << zoom) * 360.0 - 180.0


def tile_y_to_lat(y: float, zoom: int) -> float:
    return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / (1 << zoom)))))


def viewport_bounds(
    latitude: float, longitude: float, zoom: int, *, tile_radius: int = 2
) -> GeoBounds:
    center_x = lon_to_tile_x(longitude, zoom)
    center_y = lat_to_tile_y(latitude, zoom)
    return GeoBounds(
        min_latitude=tile_y_to_lat(center_y + tile_radius + 0.5, zoom),
        min_longitude=max(-180.0, tile_x_to_lon(center_x - tile_radius - 0.5, zoom)),
        max_latitude=tile_y_to_lat(center_y - tile_radius - 0.5, zoom),
        max_longitude=min(180.0, tile_x_to_lon(center_x + tile_radius + 0.5, zoom)),
    )


def _package_covers(package: OfflineMapPackage, *, latitude: float, longitude: float) -> bool:
    if None in (package.west, package.south, package.east, package.north):
        return True
    if not (float(package.south) <= latitude <= float(package.north)):
        return False
    west = float(package.west)
    east = float(package.east)
    if west <= east:
        return west <= longitude <= east
    return longitude >= west or longitude <= east
