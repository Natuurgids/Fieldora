"""Catalog-authorized access to independently owned offline map databases."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from natureai_next.domain.maps import MapArchiveSlice, OfflineMapPackage


class _MapPackageCatalog(Protocol):
    def get(self, public_id: str) -> OfflineMapPackage: ...


class CatalogMapArchiveReader:
    """Read bounded PMTiles ranges selected only by catalog public ID."""

    DEFAULT_MAX_RANGE_BYTES = 8 * 1024 * 1024

    def __init__(
        self, catalog: _MapPackageCatalog, *, max_range_bytes: int = DEFAULT_MAX_RANGE_BYTES
    ) -> None:
        if max_range_bytes <= 0:
            raise ValueError("maximum map archive range must be positive")
        self._catalog = catalog
        self._max_range_bytes = max_range_bytes

    def read(self, package_public_id: str, offset: int, length: int) -> MapArchiveSlice:
        if offset < 0:
            raise ValueError("map archive offset cannot be negative")
        if length <= 0:
            raise ValueError("map archive range length must be positive")
        if length > self._max_range_bytes:
            raise ValueError("map archive range exceeds the configured limit")

        package = self._catalog.get(package_public_id)
        if package.format != "pmtiles":
            raise ValueError("byte-range archive access is available only for PMTiles packages")
        if not package.enabled or package.status != "installed":
            raise ValueError("map archive package is not enabled and installed")

        path = Path(package.package_path)
        if not path.is_file():
            raise FileNotFoundError("installed map archive is missing")
        total_size = path.stat().st_size
        if package.verified_size_bytes is not None and total_size != package.verified_size_bytes:
            raise ValueError("installed map archive size changed after verification")
        if offset >= total_size:
            raise ValueError("map archive offset is outside the package")

        read_length = min(length, total_size - offset)
        with path.open("rb") as stream:
            stream.seek(offset)
            data = stream.read(read_length)
        if len(data) != read_length:
            raise OSError("map archive range could not be read completely")
        return MapArchiveSlice(
            package_public_id=package.public_id,
            offset=offset,
            total_size=total_size,
            data=data,
            checksum_sha256=package.observed_checksum_sha256 or package.checksum_sha256,
        )


class CatalogVectorTileReader:
    """Read complete vector tiles from an installed MBTiles database.

    The database belongs to the offline-map resource subsystem and is opened
    read-only for each request, so rendering never writes to or locks the
    Aperture operational database.
    """

    def __init__(self, catalog: _MapPackageCatalog) -> None:
        self._catalog = catalog

    def read_tile(self, package_public_id: str, zoom: int, x: int, y: int) -> bytes | None:
        import sqlite3

        if zoom < 0 or x < 0 or y < 0:
            raise ValueError("tile coordinates must be non-negative")
        limit = (1 << zoom) - 1
        if x > limit or y > limit:
            raise ValueError("tile coordinates are outside the zoom level")
        package = self._catalog.get(package_public_id)
        if package.format != "vector-mbtiles":
            raise ValueError("tile access is available only for vector MBTiles packages")
        if not package.enabled or package.status != "installed":
            raise ValueError("map package is not enabled and installed")
        path = Path(package.package_path)
        if not path.is_file():
            raise FileNotFoundError("installed vector map database is missing")
        stored_y = limit - y if package.tile_scheme == "tms" else y
        connection = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro&immutable=1",
            uri=True,
            isolation_level=None,
            timeout=1.0,
        )
        try:
            row = connection.execute(
                "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (zoom, x, stored_y),
            ).fetchone()
            return None if row is None else bytes(row[0])
        finally:
            connection.close()
