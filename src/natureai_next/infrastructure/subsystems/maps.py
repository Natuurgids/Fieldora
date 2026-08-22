"""Offline-map subsystem descriptor and catalog repository."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from natureai_next.domain.maps import OfflineMapPackage, OfflineRasterTile
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.subsystems.migrations.maps_v001_catalog import MIGRATION as V001
from natureai_next.infrastructure.subsystems.migrations.maps_v002_lifecycle import MIGRATION as V002
from natureai_next.infrastructure.subsystems.migrations.maps_v003_osm_lite import MIGRATION as V003
from natureai_next.infrastructure.subsystems.migrations.maps_v004_vector_mbtiles import (
    MIGRATION as V004,
)
from natureai_next.infrastructure.subsystems.registry import SubsystemDatabaseDescriptor

MAPS_SUBSYSTEM_KEY = "maps.offline"
MAPS_MIGRATIONS = (V001, V002, V003, V004)


def maps_descriptor(database_path: Path) -> SubsystemDatabaseDescriptor:
    return SubsystemDatabaseDescriptor(MAPS_SUBSYSTEM_KEY, database_path, MAPS_MIGRATIONS)


class OfflineMapCatalog:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def register(self, package: OfflineMapPackage) -> None:
        """Register or atomically replace one installed map package.

        Provider downloads may be converted into another installed format.  The
        catalog stores the final Aperture package, not the provider source file.
        Upsert by public ID avoids masking schema/validation errors as an
        unrelated missing-package failure during updates.
        """
        connection = self._factory.connect()
        try:
            connection.execute(
                "INSERT INTO map_packages(public_id,provider_key,package_name,package_version,format,"
                "package_path,min_zoom,max_zoom,west,south,east,north,checksum_sha256,attribution,installed_at_us,"
                "tile_scheme,data_license,attribution_url,enabled,status,verification_message,provider_metadata_json) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(public_id) DO UPDATE SET "
                "provider_key=excluded.provider_key,package_name=excluded.package_name,"
                "package_version=excluded.package_version,format=excluded.format,"
                "package_path=excluded.package_path,min_zoom=excluded.min_zoom,max_zoom=excluded.max_zoom,"
                "west=excluded.west,south=excluded.south,east=excluded.east,north=excluded.north,"
                "checksum_sha256=excluded.checksum_sha256,attribution=excluded.attribution,"
                "installed_at_us=excluded.installed_at_us,tile_scheme=excluded.tile_scheme,"
                "data_license=excluded.data_license,attribution_url=excluded.attribution_url,"
                "enabled=1,status='installed',verification_message='',provider_metadata_json=excluded.provider_metadata_json",
                (
                    package.public_id,
                    package.provider_key,
                    package.package_name,
                    package.package_version,
                    package.format,
                    package.package_path,
                    package.min_zoom,
                    package.max_zoom,
                    package.west,
                    package.south,
                    package.east,
                    package.north,
                    package.checksum_sha256,
                    package.attribution,
                    package.installed_at_us,
                    package.tile_scheme,
                    package.data_license,
                    package.attribution_url,
                    1,
                    "installed",
                    "",
                    package.provider_metadata_json,
                ),
            )
        finally:
            connection.close()

    def covering(self, latitude: float, longitude: float) -> tuple[OfflineMapPackage, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT public_id,provider_key,package_name,package_version,format,package_path,"
                "installed_at_us,attribution,min_zoom,max_zoom,west,south,east,north,checksum_sha256,"
                "enabled,status,verification_message,verified_size_bytes,observed_checksum_sha256,provider_metadata_json,"
                "tile_scheme,data_license,attribution_url "
                "FROM map_packages WHERE enabled=1 AND status='installed' AND "
                "(west IS NULL OR west<=?) AND (east IS NULL OR east>=?) AND "
                "(south IS NULL OR south<=?) AND (north IS NULL OR north>=?) "
                "ORDER BY package_name",
                (longitude, longitude, latitude, latitude),
            ).fetchall()
            return tuple(OfflineMapPackage(**dict(row)) for row in rows)
        finally:
            connection.close()

    def list_all(self) -> tuple[OfflineMapPackage, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT public_id,provider_key,package_name,package_version,format,package_path,"
                "installed_at_us,attribution,min_zoom,max_zoom,west,south,east,north,checksum_sha256,"
                "enabled,status,verification_message,verified_size_bytes,observed_checksum_sha256,provider_metadata_json,"
                "tile_scheme,data_license,attribution_url FROM map_packages ORDER BY package_name"
            ).fetchall()
            result = []
            for row in rows:
                values = dict(row)
                values["enabled"] = bool(values["enabled"])
                result.append(OfflineMapPackage(**values))
            return tuple(result)
        finally:
            connection.close()

    def remove(self, public_id: str) -> None:
        connection = self._factory.connect()
        try:
            cursor = connection.execute("DELETE FROM map_packages WHERE public_id=?", (public_id,))
            if cursor.rowcount != 1:
                raise KeyError(f"unknown offline map package: {public_id}")
        finally:
            connection.close()

    def set_enabled(self, public_id: str, enabled: bool) -> None:
        connection = self._factory.connect()
        try:
            cursor = connection.execute(
                "UPDATE map_packages SET enabled=? WHERE public_id=?",
                (1 if enabled else 0, public_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"unknown offline map package: {public_id}")
        finally:
            connection.close()

    def get(self, public_id: str) -> OfflineMapPackage:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT public_id,provider_key,package_name,package_version,format,package_path,"
                "installed_at_us,attribution,min_zoom,max_zoom,west,south,east,north,checksum_sha256,"
                "enabled,status,verification_message,verified_size_bytes,observed_checksum_sha256,provider_metadata_json,"
                "tile_scheme,data_license,attribution_url "
                "FROM map_packages WHERE public_id=?",
                (public_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown offline map package: {public_id}")
            values = dict(row)
            values["enabled"] = bool(values["enabled"])
            return OfflineMapPackage(**values)
        finally:
            connection.close()


@dataclass(frozen=True, slots=True)
class MapPackageVerification:
    public_id: str
    valid: bool
    status: str
    message: str
    size_bytes: int | None
    checksum_sha256: str | None


class OfflineMapProvider(Protocol):
    """Provider boundary for a concrete offline map format or renderer."""

    @property
    def key(self) -> str: ...

    def supports(self, package: OfflineMapPackage) -> bool: ...

    def validate_package(self, package_path: Path) -> tuple[bool, str, dict[str, object]]: ...


class GenericFileMapProvider:
    """Minimal provider used until a renderer-specific implementation is selected."""

    key = "generic.file"

    def supports(self, package: OfflineMapPackage) -> bool:
        return package.format in {"vector_bundle", "raster_bundle", "other"}

    def validate_package(self, package_path: Path) -> tuple[bool, str, dict[str, object]]:
        if not package_path.is_file():
            return False, "package file is missing", {}
        size = package_path.stat().st_size
        if size <= 0:
            return False, "package file is empty", {"size_bytes": size}
        return True, "package file is readable", {"size_bytes": size}


class MbtilesMapProvider:
    key = "mbtiles.sqlite"

    def supports(self, package: OfflineMapPackage) -> bool:
        return package.format == "mbtiles"

    def validate_package(self, package_path: Path) -> tuple[bool, str, dict[str, object]]:
        if not package_path.is_file():
            return False, "MBTiles package is missing", {}
        try:
            connection = sqlite3.connect(
                f"file:{package_path.as_posix()}?mode=ro", uri=True, isolation_level=None
            )
            try:
                names = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                    )
                }
                if "tiles" not in names:
                    return False, "MBTiles package has no tiles table or view", {}
                tile_count = int(connection.execute("SELECT COUNT(*) FROM tiles").fetchone()[0])
                metadata = {}
                if "metadata" in names:
                    metadata = {
                        str(k): str(v)
                        for k, v in connection.execute("SELECT name,value FROM metadata")
                    }
                if tile_count <= 0:
                    return (
                        False,
                        "MBTiles package contains no tiles",
                        {
                            "size_bytes": package_path.stat().st_size,
                            "tile_count": tile_count,
                            "metadata": metadata,
                        },
                    )
                required = ("bounds", "minzoom", "maxzoom", "format")
                missing = [name for name in required if not str(metadata.get(name, "")).strip()]
                if missing:
                    return (
                        False,
                        "MBTiles metadata is incomplete: " + ", ".join(missing),
                        {
                            "size_bytes": package_path.stat().st_size,
                            "tile_count": tile_count,
                            "metadata": metadata,
                        },
                    )
                try:
                    min_zoom = int(metadata["minzoom"])
                    max_zoom = int(metadata["maxzoom"])
                    bounds = tuple(float(value) for value in metadata["bounds"].split(","))
                    if len(bounds) != 4 or min_zoom < 0 or max_zoom < min_zoom:
                        raise ValueError
                except (TypeError, ValueError):
                    return (
                        False,
                        "MBTiles bounds or zoom metadata is invalid",
                        {
                            "size_bytes": package_path.stat().st_size,
                            "tile_count": tile_count,
                            "metadata": metadata,
                        },
                    )
                return (
                    True,
                    f"MBTiles package is readable ({tile_count} tiles, zoom {min_zoom}-{max_zoom})",
                    {
                        "size_bytes": package_path.stat().st_size,
                        "tile_count": tile_count,
                        "metadata": metadata,
                        "bounds": bounds,
                        "min_zoom": min_zoom,
                        "max_zoom": max_zoom,
                    },
                )
            finally:
                connection.close()
        except (OSError, sqlite3.DatabaseError) as exc:
            return False, f"invalid MBTiles package: {exc}", {}


class VectorMbtilesMapProvider(MbtilesMapProvider):
    """Validator for vector MBTiles; rendering remains a separate capability."""

    key = "openstreetmap.vector-mbtiles"

    def supports(self, package: OfflineMapPackage) -> bool:
        return package.format == "vector-mbtiles"

    def validate_package(self, package_path: Path) -> tuple[bool, str, dict[str, object]]:
        valid, message, details = super().validate_package(package_path)
        if not valid:
            return valid, message, details
        metadata = details.get("metadata", {})
        tile_format = str(metadata.get("format", "")).casefold()
        if tile_format not in {"pbf", "mvt"}:
            return False, f"unsupported vector MBTiles format: {tile_format or 'missing'}", details
        details["tile_kind"] = "vector"
        details["renderer_status"] = "pending"
        return (
            True,
            "Vector MBTiles package is valid; street-level renderer is not installed",
            details,
        )


class PmtilesMapProvider:
    """Validate a PMTiles v3 archive without coupling verification to a renderer."""

    key = "openstreetmap.pmtiles"

    def supports(self, package: OfflineMapPackage) -> bool:
        return package.format == "pmtiles"

    def validate_package(self, package_path: Path) -> tuple[bool, str, dict[str, object]]:
        if not package_path.is_file():
            return False, "PMTiles package is missing", {}
        size = package_path.stat().st_size
        if size < 127:
            return (
                False,
                "PMTiles package is too small to contain a v3 header",
                {"size_bytes": size},
            )
        with package_path.open("rb") as stream:
            header = stream.read(127)
        if header[:7] != b"PMTiles":
            return False, "PMTiles package has an invalid header", {"size_bytes": size}
        version = int(header[7])
        if version != 3:
            return (
                False,
                f"unsupported PMTiles version: {version}",
                {"size_bytes": size, "version": version},
            )
        tile_type = int(header[99])
        min_zoom = int(header[100])
        max_zoom = int(header[101])
        if tile_type != 1:
            return (
                False,
                "PMTiles package does not contain vector MVT tiles",
                {
                    "size_bytes": size,
                    "version": version,
                    "tile_type": tile_type,
                },
            )
        if min_zoom > max_zoom or max_zoom > 22:
            return (
                False,
                "PMTiles package declares an invalid zoom range",
                {
                    "size_bytes": size,
                    "version": version,
                    "min_zoom": min_zoom,
                    "max_zoom": max_zoom,
                },
            )
        for name, offset_at, length_at in (
            ("root directory", 8, 16),
            ("metadata", 24, 32),
            ("leaf directory", 40, 48),
            ("tile data", 56, 64),
        ):
            offset = int.from_bytes(header[offset_at : offset_at + 8], "little")
            length = int.from_bytes(header[length_at : length_at + 8], "little")
            if length and (offset < 127 or offset + length > size):
                return (
                    False,
                    f"PMTiles {name} range is outside the archive",
                    {
                        "size_bytes": size,
                        "version": version,
                    },
                )
        return (
            True,
            "PMTiles v3 vector package is structurally valid",
            {
                "size_bytes": size,
                "version": version,
                "tile_kind": "vector",
                "tile_type": "mvt",
                "min_zoom": min_zoom,
                "max_zoom": max_zoom,
            },
        )


class OsmLiteMbtilesProvider(MbtilesMapProvider):
    """Lightweight local reader for OSM-derived raster MBTiles packages.

    It never contacts OpenStreetMap servers. Packages must be supplied by the
    user or by a separately approved package source with offline-distribution
    rights.
    """

    key = "openstreetmap.mbtiles"
    DEFAULT_ATTRIBUTION = "© OpenStreetMap contributors"
    DEFAULT_ATTRIBUTION_URL = "https://www.openstreetmap.org/copyright"
    DEFAULT_LICENSE = "ODbL-1.0"

    def supports(self, package: OfflineMapPackage) -> bool:
        return package.format == "mbtiles" and (
            package.provider_key == self.key or package.provider_key.startswith("geofabrik.")
        )

    def validate_package(self, package_path: Path) -> tuple[bool, str, dict[str, object]]:
        valid, message, details = super().validate_package(package_path)
        if not valid:
            return valid, message, details
        metadata = details.get("metadata", {})
        tile_format = str(metadata.get("format", "png")).lower()
        if tile_format not in {"png", "jpg", "jpeg", "webp"}:
            return False, f"unsupported OSM Lite raster format: {tile_format}", details
        details["tile_format"] = tile_format
        details["attribution"] = str(metadata.get("attribution") or self.DEFAULT_ATTRIBUTION)
        details["data_license"] = str(metadata.get("license") or self.DEFAULT_LICENSE)
        return True, "OSM-compatible offline MBTiles package is readable", details

    def read_xyz_tile(
        self, package: OfflineMapPackage, zoom: int, x: int, y: int
    ) -> OfflineRasterTile | None:
        if zoom < 0 or x < 0 or y < 0:
            raise ValueError("tile coordinates must be non-negative")
        max_index = (1 << zoom) - 1
        if x > max_index or y > max_index:
            raise ValueError("tile coordinates are outside the zoom level")
        stored_y = max_index - y if package.tile_scheme == "tms" else y
        path = Path(package.package_path)
        connection = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro", uri=True, isolation_level=None
        )
        try:
            row = connection.execute(
                "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (zoom, x, stored_y),
            ).fetchone()
            if row is None:
                return None
            metadata = {}
            names = {
                str(item[0])
                for item in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                )
            }
            if "metadata" in names:
                metadata = {
                    str(k): str(v) for k, v in connection.execute("SELECT name,value FROM metadata")
                }
            tile_format = str(metadata.get("format", "png")).lower()
            media_type = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "webp": "image/webp",
            }.get(tile_format, "application/octet-stream")
            return OfflineRasterTile(
                zoom=zoom,
                x=x,
                y=y,
                data=bytes(row[0]),
                media_type=media_type,
                attribution=package.attribution
                or str(metadata.get("attribution") or self.DEFAULT_ATTRIBUTION),
                attribution_url=package.attribution_url or self.DEFAULT_ATTRIBUTION_URL,
            )
        finally:
            connection.close()


class OsmLiteOfflineMapService:
    """Minimal application-facing service for local OSM raster tiles."""

    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._catalog = OfflineMapCatalog(factory)
        self._provider = OsmLiteMbtilesProvider()

    def tile(self, package_public_id: str, zoom: int, x: int, y: int) -> OfflineRasterTile | None:
        package = self._catalog.get(package_public_id)
        if not package.enabled or package.status != "installed":
            raise ValueError("offline map package is not enabled and installed")
        if not self._provider.supports(package):
            raise ValueError("package is not an OpenStreetMap Lite MBTiles package")
        return self._provider.read_xyz_tile(package, zoom, x, y)


class OfflineMapPackageService:
    def __init__(
        self,
        factory: SqliteConnectionFactory,
        providers: tuple[OfflineMapProvider, ...] | None = None,
    ) -> None:
        self._factory = factory
        self._catalog = OfflineMapCatalog(factory)
        self._providers = providers or (
            OsmLiteMbtilesProvider(),
            VectorMbtilesMapProvider(),
            MbtilesMapProvider(),
            GenericFileMapProvider(),
        )

    def enable(self, public_id: str) -> None:
        package = self._catalog.get(public_id)
        if package.status != "installed":
            raise ValueError(f"cannot enable package in {package.status!r} state")
        self._catalog.set_enabled(public_id, True)

    def disable(self, public_id: str) -> None:
        self._catalog.set_enabled(public_id, False)

    def verify(self, public_id: str) -> MapPackageVerification:
        package = self._catalog.get(public_id)
        path = Path(package.package_path)
        provider = next((item for item in self._providers if item.supports(package)), None)
        if provider is None:
            return self._record(
                package,
                False,
                "invalid",
                "no provider supports this package format",
                None,
                None,
                {},
            )
        valid, message, metadata = provider.validate_package(path)
        size = path.stat().st_size if path.is_file() else None
        checksum = self._sha256(path) if valid else None
        if valid and package.checksum_sha256 and checksum != package.checksum_sha256:
            valid = False
            message = "package checksum does not match the catalog"
        status = "installed" if valid else ("missing" if not path.exists() else "invalid")
        return self._record(package, valid, status, message, size, checksum, metadata)

    def _record(
        self,
        package: OfflineMapPackage,
        valid: bool,
        status: str,
        message: str,
        size: int | None,
        checksum: str | None,
        metadata: dict[str, object],
    ) -> MapPackageVerification:
        try:
            declared = json.loads(package.provider_metadata_json)
        except (TypeError, json.JSONDecodeError):
            declared = {}
        merged_metadata = {**declared, **metadata}
        connection = self._factory.connect()
        try:
            connection.execute(
                "UPDATE map_packages SET status=?, verification_message=?, verified_size_bytes=?, "
                "last_verified_at_us=?, observed_checksum_sha256=?, provider_metadata_json=? WHERE public_id=?",
                (
                    status,
                    message,
                    size,
                    time.time_ns() // 1000,
                    checksum,
                    json.dumps(merged_metadata, sort_keys=True),
                    package.public_id,
                ),
            )
        finally:
            connection.close()
        return MapPackageVerification(package.public_id, valid, status, message, size, checksum)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
