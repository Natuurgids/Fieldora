"""Geofabrik OpenStreetMap provider and lightweight raster-MBTiles builder.

Geofabrik publishes regional OpenStreetMap extracts and a public hierarchy index.
Aperture downloads only leaf-region shapefile extracts and converts them locally to
small raster MBTiles packages. Public OSM tile servers are never bulk-downloaded.
"""

from __future__ import annotations

import contextlib
import gc
import hashlib
import itertools
import json
import math
import os
import shutil
import sqlite3
import tempfile
import time
import urllib.request
import zipfile
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from natureai_next.application.map_acquisition import MapCatalogEntry, MapPackageCatalog
from natureai_next.application.workspace_manager import AdaptiveWorkspaceManager

GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1.json"

_WORKER_LAYERS = None


def _worker_init(layer_paths) -> None:
    global _WORKER_LAYERS
    _WORKER_LAYERS = GeofabrikShapefileConverter._open_layers(
        tuple((token, Path(path)) for token, path in layer_paths)
    )


def _worker_render_tile(task):
    zoom, tx, ty = task
    if _WORKER_LAYERS is None:
        raise RuntimeError("render worker was not initialized")
    image = GeofabrikShapefileConverter._tile_static(_WORKER_LAYERS, zoom, tx, ty)
    out = BytesIO()
    image.save(out, format="PNG", optimize=True)
    return zoom, tx, ty, out.getvalue()


def _bbox(geometry: object) -> tuple[float, float, float, float] | None:
    if not isinstance(geometry, dict):
        return None
    coords = geometry.get("coordinates")
    points: list[tuple[float, float]] = []

    def walk(value: object) -> None:
        if isinstance(value, list | tuple):
            if (
                len(value) >= 2
                and isinstance(value[0], int | float)
                and isinstance(value[1], int | float)
            ):
                points.append((float(value[0]), float(value[1])))
            else:
                for item in value:
                    walk(item)

    walk(coords)
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


class GeofabrikCatalogProvider:
    """Load the official Geofabrik region hierarchy as an Aperture catalog."""

    def __init__(self, index_url: str = GEOFABRIK_INDEX_URL) -> None:
        self.index_url = index_url

    def load(self) -> MapPackageCatalog:
        request = urllib.request.Request(
            self.index_url, headers={"User-Agent": "Aperture/2 NatureAI-Next"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 official HTTPS endpoint
            payload = response.read()
        return self.parse(payload)

    def parse(self, payload: bytes | str) -> MapPackageCatalog:
        raw = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
        features = raw.get("features", [])
        props_by_id: dict[str, dict[str, object]] = {}
        geometry_by_id: dict[str, object] = {}
        children: dict[str, list[str]] = {}
        for feature in features:
            props = dict(feature.get("properties") or {})
            region_id = str(props.get("id") or "").strip()
            if not region_id:
                continue
            props_by_id[region_id] = props
            geometry_by_id[region_id] = feature.get("geometry")
            parent = props.get("parent")
            if parent:
                children.setdefault(str(parent), []).append(region_id)
        entries = []
        for region_id, props in props_by_id.items():
            parent = str(props["parent"]) if props.get("parent") else None
            depth = 0
            cursor = parent
            while cursor and cursor in props_by_id and depth < 20:
                depth += 1
                p = props_by_id[cursor].get("parent")
                cursor = str(p) if p else None
            region_type = "continent" if parent is None else "country" if depth == 1 else "region"
            urls = props.get("urls") if isinstance(props.get("urls"), dict) else {}
            pbf_url = str(urls.get("pbf") or "")
            # The normal user workflow deliberately downloads only provider leaf regions.
            downloadable = bool(pbf_url) and not children.get(region_id)
            bounds = _bbox(geometry_by_id.get(region_id)) or (None, None, None, None)
            entries.append(
                MapCatalogEntry(
                    entry_id=f"geofabrik:{region_id}",
                    name=str(props.get("name") or region_id.replace("-", " ").title()),
                    region_type=region_type,
                    parent_id=f"geofabrik:{parent}" if parent else None,
                    downloadable=downloadable,
                    provider_key="geofabrik.openstreetmap.pbf",
                    package_version=str(props.get("timestamp") or "current")[:10],
                    format="geofabrik-osm-pbf",
                    download_url=pbf_url,
                    min_zoom=0,
                    max_zoom=14,
                    west=bounds[0],
                    south=bounds[1],
                    east=bounds[2],
                    north=bounds[3],
                    attribution="© OpenStreetMap contributors; regional extract by Geofabrik",
                    attribution_url="https://www.openstreetmap.org/copyright",
                    data_license="ODbL-1.0",
                    tile_scheme="tms",
                    street_schema="aperture-streets-v1",
                    street_layers=("landuse", "water", "building", "transportation", "place"),
                    street_label_fields=("transportation.name", "place.name"),
                )
            )
        return MapPackageCatalog(
            "geofabrik-openstreetmap", str(raw.get("timestamp") or "current"), tuple(entries)
        )


@dataclass(frozen=True, slots=True)
class ConversionResult:
    path: Path
    sha256: str
    size_bytes: int
    min_zoom: int
    max_zoom: int


def _lon_x(lon: float, zoom: int) -> float:
    return (lon + 180.0) / 360.0 * (1 << zoom)


def _lat_y(lat: float, zoom: int) -> float:
    lat = max(-85.05112878, min(85.05112878, lat))
    rad = math.radians(lat)
    return (1.0 - math.asinh(math.tan(rad)) / math.pi) / 2.0 * (1 << zoom)


class GeofabrikShapefileConverter:
    """Convert one Geofabrik leaf-region shapefile archive to raster MBTiles."""

    def __init__(self, max_zoom: int = 10) -> None:
        self.max_zoom = max(4, min(12, max_zoom))

    def convert(
        self,
        archive: Path,
        destination: Path,
        entry: MapCatalogEntry,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> ConversionResult:
        destination.parent.mkdir(parents=True, exist_ok=True)
        workspace = AdaptiveWorkspaceManager().plan(archive.stat().st_size)
        root = Path(tempfile.mkdtemp(prefix="aperture-map-", dir=workspace.root))
        try:
            # Keep the verified archive in memory when the adaptive budget allows it.
            archive_source = (
                BytesIO(archive.read_bytes()) if workspace.mode == "memory-assisted" else archive
            )
            with zipfile.ZipFile(archive_source) as bundle:
                for member in bundle.infolist():
                    target = (root / member.filename).resolve()
                    if root.resolve() not in target.parents and target != root.resolve():
                        raise ValueError("unsafe path in Geofabrik archive")
                bundle.extractall(root)
            self._render(root, destination, entry, progress=progress, cancelled=cancelled)
        finally:
            self._cleanup_temporary_tree(root)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        return ConversionResult(destination, digest, destination.stat().st_size, 0, self.max_zoom)

    def _render(
        self,
        root: Path,
        destination: Path,
        entry: MapCatalogEntry,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        if None in (entry.west, entry.south, entry.east, entry.north):
            raise ValueError("selected Geofabrik region has no usable bounds")
        destination.unlink(missing_ok=True)
        db = sqlite3.connect(destination)
        try:
            db.executescript("""
                CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB,
                                    UNIQUE(zoom_level,tile_column,tile_row));
                CREATE INDEX tile_index ON tiles(zoom_level,tile_column,tile_row);
            """)
            metadata = {
                "name": entry.name,
                "type": "baselayer",
                "version": entry.package_version or "current",
                "description": "Aperture offline map generated from a Geofabrik OpenStreetMap extract",
                "format": "png",
                "bounds": f"{entry.west},{entry.south},{entry.east},{entry.north}",
                "minzoom": "0",
                "maxzoom": str(self.max_zoom),
                "attribution": entry.attribution,
            }
            db.executemany("INSERT INTO metadata(name,value) VALUES(?,?)", metadata.items())
            layer_paths = self._layers(root)
            report = progress or (lambda _c, _t, _m: None)
            is_cancelled = cancelled or (lambda: False)
            ranges = []
            tasks = []
            for zoom in range(0, self.max_zoom + 1):
                x0 = max(0, int(math.floor(_lon_x(float(entry.west), zoom))))
                x1 = min((1 << zoom) - 1, int(math.floor(_lon_x(float(entry.east), zoom))))
                y0 = max(0, int(math.floor(_lat_y(float(entry.north), zoom))))
                y1 = min((1 << zoom) - 1, int(math.floor(_lat_y(float(entry.south), zoom))))
                count = (x1 - x0 + 1) * (y1 - y0 + 1)
                if count > 6000:
                    raise ValueError(
                        "selected region is too large for local raster generation; choose a smaller subregion"
                    )
                ranges.append((zoom, x0, x1, y0, y1))
                tasks.extend((zoom, tx, ty) for tx in range(x0, x1 + 1) for ty in range(y0, y1 + 1))
            total_tiles = len(tasks)
            completed = 0
            configured = int(os.environ.get("NATUREAI_RENDER_WORKERS", "0") or 0)
            render_workers = configured or max(2, min(8, (os.cpu_count() or 2) // 2))
            report(
                0,
                total_tiles,
                f"Preparing map tiles with {render_workers} NatureAI Nest render workers…",
            )
            layer_args = tuple((token, str(path)) for token, path in layer_paths)
            with ProcessPoolExecutor(
                max_workers=render_workers, initializer=_worker_init, initargs=(layer_args,)
            ) as pool:
                iterator = iter(tasks)
                pending = set()
                for _ in range(min(total_tiles, render_workers * 2)):
                    try:
                        pending.add(pool.submit(_worker_render_tile, next(iterator)))
                    except StopIteration:
                        break
                while pending:
                    if is_cancelled():
                        for future in pending:
                            future.cancel()
                        raise InterruptedError("Map rendering cancelled")
                    done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
                    for future in done:
                        zoom, tx, ty, tile_data = future.result()
                        tms_y = (1 << zoom) - 1 - ty
                        db.execute(
                            "INSERT INTO tiles VALUES(?,?,?,?)", (zoom, tx, tms_y, tile_data)
                        )
                        completed += 1
                        # Durable checkpoint: commit every 32 tiles and at zoom/package boundaries.
                        if completed % 32 == 0 or completed == total_tiles:
                            db.commit()
                        report(
                            completed,
                            total_tiles,
                            f"Rendering map tiles — {completed} of {total_tiles} ({render_workers} workers)",
                        )
                        with contextlib.suppress(StopIteration):
                            pending.add(pool.submit(_worker_render_tile, next(iterator)))

        finally:
            db.close()

    @staticmethod
    def _layers(root: Path) -> tuple[tuple[str, Path], ...]:
        order = ("landuse_a", "water_a", "waterways", "railways", "roads", "places")
        found = []
        for token in order:
            candidates = sorted(root.rglob(f"*{token}*.shp"))
            if candidates:
                found.append((token, candidates[0]))
        if not found:
            raise ValueError("Geofabrik archive contains no supported map layers")
        return tuple(found)

    @staticmethod
    def _open_layers(
        layer_paths: tuple[tuple[str, Path], ...],
    ) -> tuple[tuple[str, object, tuple[str, ...]], ...]:
        try:
            import shapefile  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Offline map conversion requires the pyshp package. Re-run the Aperture installer "
                "or repair the installation before downloading Geofabrik maps."
            ) from exc
        opened = []
        try:
            for token, path in layer_paths:
                reader = shapefile.Reader(str(path), encoding="utf-8", encodingErrors="ignore")
                fields = tuple(f[0] for f in reader.fields[1:])
                opened.append((token, reader, fields))
            return tuple(opened)
        except Exception:
            GeofabrikShapefileConverter._close_layers(tuple(opened))
            raise

    @staticmethod
    def _close_layers(layers: tuple[tuple[str, object, tuple[str, ...]], ...]) -> None:
        for _token, reader, _fields in layers:
            close = getattr(reader, "close", None)
            if callable(close):
                with contextlib.suppress(Exception):
                    close()
        gc.collect()

    @staticmethod
    def _cleanup_temporary_tree(root: Path) -> None:
        if not root.exists():
            return
        for attempt in range(6):
            try:
                shutil.rmtree(root)
                return
            except FileNotFoundError:
                return
            except PermissionError:
                gc.collect()
                time.sleep(0.25 * (attempt + 1))
        # A successful map must not be invalidated by a transient Windows/antivirus lock.
        # The existing Maintenance Center cleanup will remove stale aperture-map-* folders.

    @staticmethod
    def _tile_static(
        layers: tuple[tuple[str, object, tuple[str, ...]], ...], zoom: int, tx: int, ty: int
    ) -> Image.Image:
        image = Image.new("RGB", (256, 256), (241, 239, 231))
        draw = ImageDraw.Draw(image)
        tile_bbox = (tx, ty, tx + 1, ty + 1)
        styles = {
            "landuse_a": ((224, 232, 210), (224, 232, 210), 1),
            "water_a": ((183, 214, 232), (183, 214, 232), 1),
            "waterways": (None, (112, 176, 210), 1),
            "railways": (None, (120, 120, 120), 1),
            "roads": (None, (210, 190, 150), 2 if zoom >= 8 else 1),
            "places": (None, (45, 45, 45), 1),
        }
        for token, reader, fields in layers:
            # Geofabrik extracts can contain null or malformed geometry records.
            # Read records individually so one invalid polygon cannot abort an
            # otherwise usable regional map conversion.
            try:
                record_count = len(reader)
            except Exception:
                record_count = int(getattr(reader, "numRecords", 0) or 0)
            for record_index in range(record_count):
                try:
                    sr = reader.shapeRecord(record_index)
                    shape = sr.shape
                except Exception:
                    continue
                points = getattr(shape, "points", None)
                if not points:
                    continue
                try:
                    first_lon, first_lat = points[0][:2]
                    bbox = getattr(shape, "bbox", None)
                    if bbox and len(bbox) >= 4:
                        west, south, east, north = map(float, bbox[:4])
                    else:
                        west = east = float(first_lon)
                        south = north = float(first_lat)
                    if not all(math.isfinite(v) for v in (west, south, east, north)):
                        continue
                    sx0 = _lon_x(west, zoom)
                    sy0 = _lat_y(north, zoom)
                    sx1 = _lon_x(east, zoom)
                    sy1 = _lat_y(south, zoom)
                except (TypeError, ValueError, IndexError, OverflowError):
                    continue
                if (
                    sx1 < tile_bbox[0]
                    or sx0 > tile_bbox[2]
                    or sy1 < tile_bbox[1]
                    or sy0 > tile_bbox[3]
                ):
                    continue
                fill, outline, width = styles[token]
                raw_parts = getattr(shape, "parts", None) or [0]
                try:
                    parts = [int(part) for part in raw_parts if 0 <= int(part) < len(points)]
                except (TypeError, ValueError):
                    parts = [0]
                if not parts or parts[0] != 0:
                    parts.insert(0, 0)
                parts.append(len(points))
                for start, end in itertools.pairwise(parts):
                    if end <= start:
                        continue
                    pts = []
                    for point in points[start:end]:
                        try:
                            lon, lat = float(point[0]), float(point[1])
                            if not math.isfinite(lon) or not math.isfinite(lat):
                                continue
                            pts.append(
                                ((_lon_x(lon, zoom) - tx) * 256, (_lat_y(lat, zoom) - ty) * 256)
                            )
                        except (TypeError, ValueError, IndexError, OverflowError):
                            continue
                    if token in ("landuse_a", "water_a") and len(pts) >= 3:
                        try:
                            draw.polygon(pts, fill=fill, outline=outline)
                        except (TypeError, ValueError):
                            continue
                    elif token == "places" and pts:
                        x, y = pts[0]
                        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=outline)
                        if zoom >= 8:
                            try:
                                data = dict(zip(fields, sr.record, strict=False))
                            except Exception:
                                data = {}
                            name = str(data.get("name") or "").strip()
                            if name:
                                draw.text(
                                    (x + 3, y - 6),
                                    name[:32],
                                    fill=outline,
                                    font=ImageFont.load_default(),
                                )
                    elif len(pts) >= 2:
                        try:
                            draw.line(pts, fill=outline, width=width, joint="curve")
                        except (TypeError, ValueError):
                            continue
        return image


def verify_geofabrik_md5(archive: Path, source_url: str) -> None:
    """Verify the provider's published MD5 sidecar when available."""
    request = urllib.request.Request(
        source_url + ".md5", headers={"User-Agent": "Aperture/2 NatureAI-Next"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 official HTTPS endpoint
            expected = response.read().decode("ascii", "ignore").strip().split()[0].lower()
    except Exception:
        return
    digest = hashlib.md5(usedforsecurity=False)
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    observed = digest.hexdigest()
    if expected and observed != expected:
        raise ValueError("Geofabrik extract failed provider checksum verification")
