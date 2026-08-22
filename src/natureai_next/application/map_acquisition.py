"""Offline map catalog browsing and local package acquisition.

The service is intentionally provider-neutral.  A catalog describes a hierarchy
and points to prebuilt, licensed Aperture-compatible MBTiles packages.  It never
bulk-downloads tiles from public OpenStreetMap tile servers.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path

from natureai_next.domain.maps import OfflineMapPackage
from natureai_next.ports.map_acquisition import OfflineMapCatalogPort, OfflineMapPackagePort
from natureai_next.ports.vector_map_converter import VectorMapConverter


@dataclass(frozen=True, slots=True)
class MapCatalogEntry:
    entry_id: str
    name: str
    region_type: str
    parent_id: str | None
    downloadable: bool
    provider_key: str = "openstreetmap.mbtiles"
    package_version: str = ""
    format: str = "mbtiles"
    download_url: str = ""
    download_size_bytes: int | None = None
    installed_size_bytes: int | None = None
    min_zoom: int | None = None
    max_zoom: int | None = None
    west: float | None = None
    south: float | None = None
    east: float | None = None
    north: float | None = None
    sha256: str = ""
    attribution: str = "© OpenStreetMap contributors"
    attribution_url: str = "https://www.openstreetmap.org/copyright"
    data_license: str = "ODbL-1.0"
    tile_scheme: str = "tms"
    street_schema: str = ""
    street_layers: tuple[str, ...] = ()
    street_label_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MapPackageCatalog:
    catalog_id: str
    catalog_version: str
    entries: tuple[MapCatalogEntry, ...]

    def children(self, parent_id: str | None) -> tuple[MapCatalogEntry, ...]:
        return tuple(
            sorted(
                (e for e in self.entries if e.parent_id == parent_id),
                key=lambda e: e.name.casefold(),
            )
        )

    def entry(self, entry_id: str) -> MapCatalogEntry:
        for entry in self.entries:
            if entry.entry_id == entry_id:
                return entry
        raise KeyError(entry_id)


class MapCatalogLoader:
    """Load and validate a package catalog from a local file or HTTPS URL."""

    def load(self, source: str | Path) -> MapPackageCatalog:
        if isinstance(source, Path) or not str(source).lower().startswith(("https://", "http://")):
            payload = Path(source).read_bytes()
        else:
            request = urllib.request.Request(
                str(source), headers={"User-Agent": "Aperture/2 offline-map-catalog"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - explicit user/configured URL
                payload = response.read()
        return self.parse(payload)

    def parse(self, payload: bytes | str) -> MapPackageCatalog:
        raw = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
        entries = tuple(self._entry(item) for item in raw.get("entries", ()))
        catalog = MapPackageCatalog(
            catalog_id=str(raw.get("catalog_id") or "offline-maps"),
            catalog_version=str(raw.get("catalog_version") or "1"),
            entries=entries,
        )
        self._validate(catalog)
        return catalog

    @staticmethod
    def _entry(item: dict[str, object]) -> MapCatalogEntry:
        bounds = item.get("bounds") or (None, None, None, None)
        if not isinstance(bounds, list | tuple) or len(bounds) != 4:
            raise ValueError("map catalog bounds must contain west,south,east,north")
        return MapCatalogEntry(
            entry_id=str(item["entry_id"]),
            name=str(item["name"]),
            region_type=str(item.get("region_type") or "region"),
            parent_id=str(item["parent_id"]) if item.get("parent_id") is not None else None,
            downloadable=bool(item.get("downloadable", False)),
            provider_key=str(item.get("provider_key") or "openstreetmap.mbtiles"),
            package_version=str(item.get("package_version") or ""),
            format=str(item.get("format") or "mbtiles"),
            download_url=str(item.get("download_url") or ""),
            download_size_bytes=int(item["download_size_bytes"])
            if item.get("download_size_bytes") is not None
            else None,
            installed_size_bytes=int(item["installed_size_bytes"])
            if item.get("installed_size_bytes") is not None
            else None,
            min_zoom=int(item["min_zoom"]) if item.get("min_zoom") is not None else None,
            max_zoom=int(item["max_zoom"]) if item.get("max_zoom") is not None else None,
            west=float(bounds[0]) if bounds[0] is not None else None,
            south=float(bounds[1]) if bounds[1] is not None else None,
            east=float(bounds[2]) if bounds[2] is not None else None,
            north=float(bounds[3]) if bounds[3] is not None else None,
            sha256=str(item.get("sha256") or "").lower(),
            attribution=str(item.get("attribution") or "© OpenStreetMap contributors"),
            attribution_url=str(
                item.get("attribution_url") or "https://www.openstreetmap.org/copyright"
            ),
            data_license=str(item.get("data_license") or "ODbL-1.0"),
            tile_scheme=str(item.get("tile_scheme") or "tms"),
            street_schema=str(item.get("street_schema") or ""),
            street_layers=tuple(
                str(value) for value in item.get("street_layers", ()) if isinstance(value, str)
            ),
            street_label_fields=tuple(
                str(value)
                for value in item.get("street_label_fields", ())
                if isinstance(value, str)
            ),
        )

    @staticmethod
    def _validate(catalog: MapPackageCatalog) -> None:
        ids = {entry.entry_id for entry in catalog.entries}
        if len(ids) != len(catalog.entries):
            raise ValueError("map catalog contains duplicate entry IDs")
        for entry in catalog.entries:
            if entry.parent_id is not None and entry.parent_id not in ids:
                raise ValueError(f"unknown parent {entry.parent_id!r} for {entry.entry_id!r}")
            if entry.downloadable:
                if entry.format not in {
                    "mbtiles",
                    "vector-mbtiles",
                    "pmtiles",
                    "geofabrik-shapefile",
                    "geofabrik-osm-pbf",
                }:
                    raise ValueError(f"unsupported downloadable map format for {entry.entry_id!r}")
                if not entry.download_url.lower().startswith("https://"):
                    raise ValueError(
                        f"downloadable package {entry.entry_id!r} requires an HTTPS URL"
                    )
                if entry.format in {"mbtiles", "vector-mbtiles", "pmtiles"} and (
                    len(entry.sha256) != 64
                    or any(c not in "0123456789abcdef" for c in entry.sha256)
                ):
                    raise ValueError(
                        f"downloadable map package {entry.entry_id!r} requires a SHA-256 checksum"
                    )
                if entry.street_schema:
                    from natureai_next.domain.maps import (
                        StreetPackageProfile,
                        validate_street_package_profile,
                    )

                    valid, message = validate_street_package_profile(
                        StreetPackageProfile(
                            entry.street_schema,
                            frozenset(entry.street_layers),
                            frozenset(entry.street_label_fields),
                            entry.max_zoom,
                            entry.attribution,
                            entry.data_license,
                        )
                    )
                    if not valid:
                        raise ValueError(
                            f"invalid street metadata for {entry.entry_id!r}: {message}"
                        )


@dataclass(frozen=True, slots=True)
class MapStorageEstimate:
    package_count: int
    download_bytes: int
    installed_bytes: int
    temporary_bytes: int
    free_bytes: int
    reserve_bytes: int = 0
    unknown_size_count: int = 0

    @property
    def sufficient_space(self) -> bool:
        return self.free_bytes >= self.installed_bytes + self.temporary_bytes + self.reserve_bytes


@dataclass(frozen=True, slots=True)
class MapBundleImportResult:
    bundle_name: str
    installed_package_ids: tuple[str, ...]
    installed_bytes: int


@dataclass(frozen=True, slots=True)
class MapAcquisitionResult:
    package_public_id: str
    package_path: Path
    downloaded_bytes: int
    resumed: bool


class OfflineMapAcquisitionService:
    """Download, verify, atomically install, and remove offline map packages."""

    def __init__(
        self,
        catalog: OfflineMapCatalogPort,
        packages: OfflineMapPackagePort,
        package_root: Path,
        vector_converter: VectorMapConverter | None = None,
    ) -> None:
        self._catalog = catalog
        self._packages = packages
        self._package_root = package_root
        self._vector_converter = vector_converter

    def install(
        self,
        entry: MapCatalogEntry,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> MapAcquisitionResult:
        if not entry.downloadable:
            raise ValueError("selected catalog entry is navigational and cannot be downloaded")
        if entry.format == "geofabrik-osm-pbf" and self._vector_converter is None:
            raise RuntimeError(
                "Street-level map preparation requires the open-source Planetiler toolchain; install or repair map tools before downloading"
            )
        self._package_root.mkdir(parents=True, exist_ok=True)
        report = progress or (lambda _c, _t, _m: None)
        is_cancelled = cancelled or (lambda: False)

        # Inventory is always the first phase. A verified current package is
        # reused without contacting the provider or rendering it again.
        report(0, 100, "Checking installed offline map…")
        try:
            installed = self._catalog.get(entry.entry_id)
        except KeyError:
            installed = None
        if installed is not None and installed.package_version == entry.package_version:
            verification = self._packages.verify(entry.entry_id)
            if verification.valid:
                self._packages.enable(entry.entry_id)
                report(100, 100, "Installed offline map is current; no download required")
                return MapAcquisitionResult(entry.entry_id, Path(installed.package_path), 0, False)

        safe_id = entry.entry_id.replace(":", "-").replace("/", "-")
        installed_suffix = ".pmtiles" if entry.format == "pmtiles" else ".mbtiles"
        final_path = (
            self._package_root / f"{safe_id}-{entry.package_version or 'current'}{installed_suffix}"
        )
        source_suffix = (
            ".zip"
            if entry.format == "geofabrik-shapefile"
            else ".osm.pbf"
            if entry.format == "geofabrik-osm-pbf"
            else installed_suffix
        )
        partial_path = (
            self._package_root
            / f"{safe_id}-{entry.package_version or 'current'}{source_suffix}.partial"
        )
        resumed = partial_path.exists() and partial_path.stat().st_size > 0
        downloaded = 0
        if entry.format == "geofabrik-osm-pbf":
            # Preserve and resume the regional OSM source independently from
            # Planetiler output. A completed source remains cached so Retry
            # never downloads it again and subsequent builds can run offline.
            source_path = partial_path.with_suffix("")
            if source_path.is_file() and source_path.stat().st_size > 0:
                resumed = True
                report(30, 100, "Using previously downloaded OpenStreetMap source…")
            else:
                report(2, 100, "Downloading regional OpenStreetMap source…")
                downloaded = self._download(
                    entry.download_url,
                    partial_path,
                    progress=report,
                    cancelled=is_cancelled,
                    vector_conversion=True,
                )
                if is_cancelled():
                    raise InterruptedError("Map preparation cancelled")
                # Geofabrik publishes MD5 sidecars for regional PBF extracts.
                from natureai_next.application.geofabrik_maps import verify_geofabrik_md5

                report(31, 100, "Verifying downloaded OpenStreetMap source…")
                verify_geofabrik_md5(partial_path, entry.download_url)
                os.replace(partial_path, source_path)

            def conversion_progress(current: int, total: int, message: str) -> None:
                fraction = 0.0 if total <= 0 else min(1.0, current / total)
                report(35 + int(fraction * 60), 100, message)

            assert self._vector_converter is not None
            result = self._vector_converter.convert(
                source_path,
                final_path,
                entry,
                progress=conversion_progress,
                cancelled=is_cancelled,
            )
            observed = result.sha256
            min_zoom, max_zoom = result.min_zoom, result.max_zoom
        else:
            report(2, 100, "Connecting to map provider…")
            downloaded = self._download(
                entry.download_url,
                partial_path,
                progress=report,
                cancelled=is_cancelled,
                vector_conversion=False,
            )
            if is_cancelled():
                raise InterruptedError("Map preparation cancelled")
            report(30, 100, "Verifying downloaded source…")
            if entry.format == "geofabrik-shapefile":
                from natureai_next.application.geofabrik_maps import (
                    GeofabrikShapefileConverter,
                    verify_geofabrik_md5,
                )

                verify_geofabrik_md5(partial_path, entry.download_url)
                report(35, 100, "Extracting and preparing map layers…")

                def conversion_progress(current: int, total: int, message: str) -> None:
                    fraction = 0.0 if total <= 0 else min(1.0, current / total)
                    report(40 + int(fraction * 55), 100, message)

                result = GeofabrikShapefileConverter().convert(
                    partial_path,
                    final_path,
                    entry,
                    progress=conversion_progress,
                    cancelled=is_cancelled,
                )
                partial_path.unlink(missing_ok=True)
                observed = result.sha256
                min_zoom, max_zoom = result.min_zoom, result.max_zoom
            else:
                report(35, 100, "Verifying package checksum…")
                observed = self._sha256(partial_path)
                if observed != entry.sha256:
                    raise ValueError("downloaded map package checksum does not match the catalog")
                os.replace(partial_path, final_path)
                min_zoom, max_zoom = entry.min_zoom, entry.max_zoom
        if is_cancelled():
            final_path.unlink(missing_ok=True)
            raise InterruptedError("Map preparation cancelled")
        report(96, 100, "Registering offline map package…")
        installed_format = (
            "mbtiles"
            if entry.format == "geofabrik-shapefile"
            else "vector-mbtiles"
            if entry.format == "geofabrik-osm-pbf"
            else entry.format
        )
        package = OfflineMapPackage(
            public_id=entry.entry_id,
            provider_key=(
                "openstreetmap.mbtiles"
                if installed_format == "mbtiles"
                else "openstreetmap.vector-mbtiles"
                if installed_format == "vector-mbtiles"
                else entry.provider_key
            ),
            package_name=entry.name,
            package_version=entry.package_version,
            format=installed_format,
            package_path=str(final_path),
            installed_at_us=__import__("time").time_ns() // 1000,
            attribution=entry.attribution,
            min_zoom=min_zoom,
            max_zoom=max_zoom,
            west=entry.west,
            south=entry.south,
            east=entry.east,
            north=entry.north,
            checksum_sha256=observed,
            tile_scheme=entry.tile_scheme,
            data_license=entry.data_license,
            attribution_url=entry.attribution_url,
            provider_metadata_json=self._street_metadata(entry),
        )
        self._catalog.register(package)
        verification = self._packages.verify(entry.entry_id)
        if not verification.valid:
            final_path.unlink(missing_ok=True)
            raise ValueError(verification.message)
        self._packages.enable(entry.entry_id)
        if installed is not None:
            self._remove_superseded_file(Path(installed.package_path), final_path)
        report(100, 100, "Offline map ready")
        return MapAcquisitionResult(entry.entry_id, final_path, downloaded, resumed)

    def estimate(self, entries: Iterable[MapCatalogEntry]) -> MapStorageEstimate:
        selected = tuple(entry for entry in entries if entry.downloadable)
        download = sum(entry.download_size_bytes or 0 for entry in selected)
        installed = sum(
            entry.installed_size_bytes or entry.download_size_bytes or 0 for entry in selected
        )
        temporary = download
        unknown_vectors = sum(
            1
            for entry in selected
            if entry.format == "geofabrik-osm-pbf" and not entry.download_size_bytes
        )
        # Geofabrik's index does not publish extract sizes. Reserve a safe
        # per-region envelope for the source, staged MBTiles, and headroom;
        # the response Content-Length replaces this with an exact gate before
        # any response body is written.
        reserve = unknown_vectors * 8 * 1024**3
        self._package_root.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(self._package_root).free
        return MapStorageEstimate(
            len(selected), download, installed, temporary, free, reserve, unknown_vectors
        )

    def install_file(self, entry: MapCatalogEntry, source_path: Path) -> MapAcquisitionResult:
        if not entry.downloadable:
            raise ValueError("selected catalog entry is navigational and cannot be installed")
        expected_suffix = ".pmtiles" if entry.format == "pmtiles" else ".mbtiles"
        if source_path.suffix.lower() != expected_suffix:
            raise ValueError(f"offline map package must use the {expected_suffix} extension")
        observed = self._sha256(source_path)
        if observed != entry.sha256:
            raise ValueError(f"map package checksum mismatch for {entry.name}")
        self._package_root.mkdir(parents=True, exist_ok=True)
        final_path = (
            self._package_root / f"{entry.entry_id}-{entry.package_version}{expected_suffix}"
        )
        staged_path = final_path.with_suffix(final_path.suffix + ".installing")
        shutil.copy2(source_path, staged_path)
        os.replace(staged_path, final_path)
        package = OfflineMapPackage(
            public_id=entry.entry_id,
            provider_key=entry.provider_key,
            package_name=entry.name,
            package_version=entry.package_version,
            format=entry.format,
            package_path=str(final_path),
            installed_at_us=__import__("time").time_ns() // 1000,
            attribution=entry.attribution,
            min_zoom=entry.min_zoom,
            max_zoom=entry.max_zoom,
            west=entry.west,
            south=entry.south,
            east=entry.east,
            north=entry.north,
            checksum_sha256=entry.sha256,
            tile_scheme=entry.tile_scheme,
            data_license=entry.data_license,
            attribution_url=entry.attribution_url,
            provider_metadata_json=self._street_metadata(entry),
        )
        try:
            self._catalog.register(package)
        except Exception:
            self.remove(entry.entry_id, remove_file=False)
            self._catalog.register(package)
        verification = self._packages.verify(entry.entry_id)
        if not verification.valid:
            final_path.unlink(missing_ok=True)
            raise ValueError(verification.message)
        self._packages.enable(entry.entry_id)
        return MapAcquisitionResult(entry.entry_id, final_path, source_path.stat().st_size, False)

    def import_openseamap_mbtiles(self, source_path: Path) -> MapAcquisitionResult:
        """Verify and install a user-supplied OpenSeaMap raster overlay.

        Public OpenSeaMap tile servers are deliberately never scraped here. The
        administrator supplies one complete MBTiles database, which is copied
        into Fieldora-owned storage only after structural validation.
        """
        from natureai_next.infrastructure.subsystems.maps import MbtilesMapProvider

        if source_path.suffix.casefold() != ".mbtiles":
            raise ValueError("OpenSeaMap overlays must use the .mbtiles extension")
        valid, message, details = MbtilesMapProvider().validate_package(source_path)
        if not valid:
            raise ValueError(message)
        metadata = details.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("OpenSeaMap MBTiles metadata is unavailable")
        tile_format = str(metadata.get("format") or "").casefold()
        if tile_format not in {"png", "webp"}:
            raise ValueError(
                "OpenSeaMap overlays must contain transparent PNG or WebP raster tiles"
            )
        bounds = details.get("bounds")
        if not isinstance(bounds, tuple) or len(bounds) != 4:
            raise ValueError("OpenSeaMap MBTiles bounds are unavailable")
        checksum = self._sha256(source_path)
        version = str(metadata.get("version") or metadata.get("timestamp") or "current")
        entry = MapCatalogEntry(
            # The entry id becomes part of the installed MBTiles filename.
            # A colon is illegal in Windows filenames, so keep the stable id
            # portable across every supported platform.
            entry_id=f"openseamap-{checksum[:16]}",
            name=str(metadata.get("name") or f"OpenSeaMap — {source_path.stem}"),
            region_type="nautical-overlay",
            parent_id=None,
            downloadable=True,
            provider_key="openseamap.seamark.mbtiles",
            package_version=version,
            format="mbtiles",
            download_url="https://openseamap.org/offline-import",
            min_zoom=int(details["min_zoom"]),
            max_zoom=int(details["max_zoom"]),
            west=float(bounds[0]),
            south=float(bounds[1]),
            east=float(bounds[2]),
            north=float(bounds[3]),
            sha256=checksum,
            attribution="OpenSeaMap contributors · OpenStreetMap contributors",
            attribution_url="https://www.openseamap.org/",
            data_license="ODbL-1.0",
            tile_scheme=(
                str(metadata.get("scheme") or "tms").casefold()
                if str(metadata.get("scheme") or "tms").casefold() in {"tms", "xyz"}
                else "tms"
            ),
        )
        result = self.install_file(entry, source_path)
        package = self._catalog.get(result.package_public_id)
        declared = json.loads(package.provider_metadata_json)
        declared.update(
            {
                "map_role": "nautical-overlay",
                "source_project": "OpenSeaMap",
                "navigation_status": "reference-only",
                "source_filename": source_path.name,
            }
        )
        self._catalog.register(
            replace(package, provider_metadata_json=json.dumps(declared, sort_keys=True))
        )
        self._packages.verify(result.package_public_id)
        self._packages.enable(result.package_public_id)
        return result

    def import_bundle(self, bundle_path: Path) -> MapBundleImportResult:
        if bundle_path.suffix.lower() != ".apkg":
            raise ValueError("offline map bundles must use the .apkg extension")
        with zipfile.ZipFile(bundle_path, "r") as archive:
            try:
                manifest = json.loads(archive.read("bundle.json").decode("utf-8"))
            except KeyError as exc:
                raise ValueError("map bundle does not contain bundle.json") from exc
            if (
                manifest.get("bundle_format") != "aperture-map-bundle"
                or int(manifest.get("schema_version", 0)) != 1
            ):
                raise ValueError("unsupported Aperture map bundle format")
            packages = manifest.get("packages")
            if not isinstance(packages, list) or not packages:
                raise ValueError("map bundle contains no packages")
            installed: list[str] = []
            total = 0
            with tempfile.TemporaryDirectory(prefix="aperture-map-bundle-") as temp_dir:
                root = Path(temp_dir)
                for item in packages:
                    if not isinstance(item, dict):
                        raise ValueError("invalid map bundle package entry")
                    member = str(item.get("package_path") or "")
                    member_path = Path(member)
                    if (
                        member_path.is_absolute()
                        or ".." in member_path.parts
                        or member_path.suffix.lower() not in {".mbtiles", ".pmtiles"}
                    ):
                        raise ValueError("unsafe or invalid map bundle package path")
                    entry_data = dict(item)
                    entry_data.pop("package_path", None)
                    entry_data["downloadable"] = True
                    entry_data.setdefault("download_url", "https://bundle.invalid/package.mbtiles")
                    entry = MapCatalogLoader._entry(entry_data)
                    target = root / member_path.name
                    with archive.open(member, "r") as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                    result = self.install_file(entry, target)
                    installed.append(result.package_public_id)
                    total += result.package_path.stat().st_size
            return MapBundleImportResult(
                bundle_name=str(manifest.get("name") or bundle_path.stem),
                installed_package_ids=tuple(installed),
                installed_bytes=total,
            )

    def remove(self, package_public_id: str, *, remove_file: bool = True) -> int:
        package = self._catalog.get(package_public_id)
        path = Path(package.package_path)
        reclaimed = path.stat().st_size if path.is_file() else 0
        self._catalog.remove(package_public_id)
        if remove_file:
            safe_id = package.public_id.replace(":", "-").replace("/", "-")
            base = f"{safe_id}-{package.package_version or 'current'}"
            for suffix in (
                ".pmtiles",
                ".mbtiles",
                ".osm.pbf.partial",
                ".zip.partial",
                ".pmtiles.partial",
                ".mbtiles.partial",
                ".converting.pmtiles",
                ".converting.log",
            ):
                candidate = self._package_root / f"{base}{suffix}"
                if self._owned_package_path(candidate):
                    candidate.unlink(missing_ok=True)
        return reclaimed

    def _remove_superseded_file(self, previous: Path, replacement: Path) -> None:
        if previous == replacement or not self._owned_package_path(previous):
            return
        previous.unlink(missing_ok=True)

    def _owned_package_path(self, path: Path) -> bool:
        try:
            return path.resolve().parent == self._package_root.resolve()
        except OSError:
            return False

    @staticmethod
    def _download(
        url: str,
        partial_path: Path,
        *,
        progress: Callable[[int, int, str], None],
        cancelled: Callable[[], bool],
        vector_conversion: bool = False,
    ) -> int:
        existing = partial_path.stat().st_size if partial_path.exists() else 0
        headers = {"User-Agent": "Aperture/2 offline-map-downloader"}
        if existing:
            headers["Range"] = f"bytes={existing}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=60)  # noqa: S310 - catalog-validated HTTPS URL
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and existing:
                return 0
            raise
        with response:
            status = getattr(response, "status", None)
            append = existing > 0 and status == 206
            if existing and not append:
                existing = 0
            length = response.headers.get("Content-Length")
            total_bytes = existing + int(length) if length and length.isdigit() else 0
            if total_bytes:
                required = OfflineMapAcquisitionService._required_download_space(
                    total_bytes, existing, vector_conversion=vector_conversion
                )
                free = shutil.disk_usage(partial_path.parent).free
                if free < required:
                    raise OSError(
                        "Insufficient storage for offline map preparation: "
                        f"{required / 1024**3:.1f} GB required, "
                        f"{free / 1024**3:.1f} GB available"
                    )
            mode = "ab" if append else "wb"
            written = 0
            started = __import__("time").monotonic()
            last_report = 0.0
            with partial_path.open(mode) as stream:
                while True:
                    if cancelled():
                        raise InterruptedError("Map download cancelled")
                    block = response.read(4 * 1024 * 1024)
                    if not block:
                        break
                    stream.write(block)
                    written += len(block)
                    now = __import__("time").monotonic()
                    if now - last_report >= 1.0:
                        transferred = existing + written
                        elapsed = max(0.001, now - started)
                        speed = written / elapsed
                        if total_bytes:
                            pct = min(29, int((transferred / total_bytes) * 30))
                            message = f"Downloading source — {transferred / 1024**2:.1f} of {total_bytes / 1024**2:.1f} MB at {speed / 1024**2:.1f} MB/s"
                        else:
                            pct = 1
                            message = f"Downloading source — {transferred / 1024**2:.1f} MB at {speed / 1024**2:.1f} MB/s"
                        progress(pct, 100, message)
                        last_report = now
            progress(30, 100, "Download complete")
            return written

    @staticmethod
    def _required_download_space(
        total_bytes: int, existing_bytes: int, *, vector_conversion: bool
    ) -> int:
        remaining = max(0, total_bytes - existing_bytes)
        if not vector_conversion:
            return remaining + 256 * 1024**2
        estimated_output = max(total_bytes * 2, 512 * 1024**2)
        return remaining + estimated_output + 512 * 1024**2

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _street_metadata(entry: MapCatalogEntry) -> str:
        if not entry.street_schema:
            return "{}"
        return json.dumps(
            {
                "schema": entry.street_schema,
                "layers": list(entry.street_layers),
                "label_fields": list(entry.street_label_fields),
            },
            sort_keys=True,
        )
