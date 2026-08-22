"""Offline-map workspace query adapter."""

from __future__ import annotations

import json

from natureai_next.domain.maps import (
    MapPackageCapability,
    StreetPackageProfile,
    validate_street_package_profile,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.subsystems.maps import OfflineMapCatalog, OsmLiteOfflineMapService
from natureai_next.infrastructure.subsystems.vector_renderer import QtWebEngineVectorRendererProbe
from natureai_next.ports.vector_renderer import VectorRendererProbe


class SqliteOfflineMapQuery:
    def __init__(
        self,
        factory: SqliteConnectionFactory,
        vector_renderer_probe: VectorRendererProbe | None = None,
    ) -> None:
        self._catalog = OfflineMapCatalog(factory)
        self._tiles = OsmLiteOfflineMapService(factory)
        self._vector_renderer_probe = vector_renderer_probe or QtWebEngineVectorRendererProbe()

    def covering(self, latitude: float, longitude: float):
        return self._catalog.covering(latitude, longitude)

    def list_all(self):
        return self._catalog.list_all()

    def get(self, public_id: str):
        return self._catalog.get(public_id)

    def capabilities(self):
        result = []
        vector_readiness = None
        for package in self._catalog.list_all():
            if package.format == "mbtiles":
                result.append(
                    MapPackageCapability(
                        package.public_id,
                        package.package_name,
                        package.format,
                        package.enabled and package.status == "installed",
                        "aperture.raster-mbtiles",
                        package.status,
                        "Ready in the current raster renderer"
                        if package.status == "installed"
                        else package.verification_message,
                        package.max_zoom,
                    )
                )
            elif package.format in {"vector-mbtiles", "pmtiles"}:
                try:
                    metadata = json.loads(package.provider_metadata_json)
                except (TypeError, json.JSONDecodeError):
                    metadata = {}
                conforms, conformance_message = validate_street_package_profile(
                    StreetPackageProfile(
                        schema=str(metadata.get("schema", "")),
                        layers=frozenset(
                            str(value)
                            for value in metadata.get("layers", ())
                            if isinstance(value, str)
                        ),
                        label_fields=frozenset(
                            str(value)
                            for value in metadata.get("label_fields", ())
                            if isinstance(value, str)
                        ),
                        max_zoom=package.max_zoom,
                        attribution=package.attribution,
                        data_license=package.data_license,
                    )
                )
                if not conforms:
                    result.append(
                        MapPackageCapability(
                            package.public_id,
                            package.package_name,
                            package.format,
                            False,
                            None,
                            "schema_incompatible",
                            conformance_message,
                            package.max_zoom,
                        )
                    )
                    continue
                if vector_readiness is None:
                    vector_readiness = self._vector_renderer_probe.readiness()
                ready = (
                    package.enabled
                    and package.status == "installed"
                    and vector_readiness.status == "renderer_ready"
                    and vector_readiness.webengine_available
                    and vector_readiness.assets_available
                    and vector_readiness.archive_bridge_available
                )
                result.append(
                    MapPackageCapability(
                        package.public_id,
                        package.package_name,
                        package.format,
                        ready,
                        "aperture.maplibre-mbtiles" if ready else None,
                        vector_readiness.status,
                        vector_readiness.message,
                        package.max_zoom,
                    )
                )
            else:
                result.append(
                    MapPackageCapability(
                        package.public_id,
                        package.package_name,
                        package.format,
                        False,
                        None,
                        "unsupported",
                        "No installed renderer supports this package format",
                        package.max_zoom,
                    )
                )
        return tuple(result)

    def tile(self, package_public_id: str, zoom: int, x: int, y: int):
        return self._tiles.tile(package_public_id, zoom, x, y)
