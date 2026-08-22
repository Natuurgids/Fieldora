"""Application-facing map workspace query contracts."""

from __future__ import annotations

from typing import Protocol

from natureai_next.domain.maps import MapPackageCapability, OfflineMapPackage, OfflineRasterTile
from natureai_next.domain.spatial_intelligence import (
    GeoBounds,
    MonitoringSiteSummary,
    SpatialAsset,
    SpatialAssetCluster,
    SpatialObservation,
)


class OfflineMapQuery(Protocol):
    def covering(self, latitude: float, longitude: float) -> tuple[OfflineMapPackage, ...]: ...
    def list_all(self) -> tuple[OfflineMapPackage, ...]: ...
    def get(self, public_id: str) -> OfflineMapPackage: ...
    def capabilities(self) -> tuple[MapPackageCapability, ...]: ...
    def tile(
        self, package_public_id: str, zoom: int, x: int, y: int
    ) -> OfflineRasterTile | None: ...


class SpatialMapQuery(Protocol):
    def observations_in_bounds(
        self, bounds: GeoBounds, *, limit: int = 5000
    ) -> tuple[SpatialObservation, ...]: ...
    def assets_in_bounds(
        self, bounds: GeoBounds, *, limit: int = 5000
    ) -> tuple[SpatialAsset, ...]: ...
    def asset_clusters_in_bounds(
        self, bounds: GeoBounds, *, zoom: int, limit: int = 5000
    ) -> tuple[SpatialAssetCluster, ...]: ...
    def list_sites_in_bounds(
        self, bounds: GeoBounds, *, limit: int = 1000
    ) -> tuple[MonitoringSiteSummary, ...]: ...
