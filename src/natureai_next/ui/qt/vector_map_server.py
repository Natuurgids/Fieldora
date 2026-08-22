"""Loopback-only HTTP transport for independent vector MBTiles databases.

MapLibre workers are most reliable when vector tiles, JavaScript, CSS, and the
map document share an ordinary HTTP origin.  This server binds only to
127.0.0.1, uses an unguessable path token, opens the selected MBTiles database
read-only per request, and never touches the Aperture operational database.
"""

from __future__ import annotations

import contextlib
import gzip
import mimetypes
import secrets
import sqlite3
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

EMPTY_MVT = b"\x1a\x0d\x0a\x06_empty\x28\x80\x20\x78\x02"


def _tile_bytes_or_none(package: Any, zoom: int, x: int, y: int) -> bytes | None:
    if zoom < 0 or x < 0 or y < 0:
        raise ValueError("tile coordinates must be non-negative")
    limit = (1 << zoom) - 1
    if x > limit or y > limit:
        return None
    path = Path(package.package_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    stored_y = limit - y if getattr(package, "tile_scheme", "tms") == "tms" else y
    connection = sqlite3.connect(
        f"file:{path.as_posix()}?mode=ro&immutable=1",
        uri=True,
        isolation_level=None,
        timeout=2.0,
    )
    try:
        row = connection.execute(
            "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (zoom, x, stored_y),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    data = bytes(row[0])
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    elif len(data) >= 2 and data[0] == 0x78:
        with contextlib.suppress(zlib.error):
            data = zlib.decompress(data)
    return data or None


def _package_covers_tile(
    package: Any, zoom: int, x: int, y: int, *, composite: bool = True
) -> bool:
    # Regional OSM extracts share the global XYZ grid. In composite mode they
    # remain eligible at their declared zooms; correctness comes from merging
    # every intersecting tile, not selecting a single regional winner.
    if getattr(package, "min_zoom", None) is not None and zoom < int(package.min_zoom):
        return False
    if getattr(package, "max_zoom", None) is not None and zoom > int(package.max_zoom):
        return False
    if None in (
        getattr(package, "west", None),
        getattr(package, "south", None),
        getattr(package, "east", None),
        getattr(package, "north", None),
    ):
        return True
    from natureai_next.application.map_workspace import tile_x_to_lon, tile_y_to_lat

    tile_west = tile_x_to_lon(x, zoom)
    tile_east = tile_x_to_lon(x + 1, zoom)
    tile_north = tile_y_to_lat(y, zoom)
    tile_south = tile_y_to_lat(y + 1, zoom)
    south, north = float(package.south), float(package.north)
    if tile_north < south or tile_south > north:
        return False
    west, east = float(package.west), float(package.east)
    if west <= east:
        return not (tile_east < west or tile_west > east)
    return tile_east >= west or tile_west <= east


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
        if shift > 63:
            raise ValueError("invalid protobuf varint")
    raise ValueError("truncated protobuf varint")


def _varint(value: int) -> bytes:
    output = bytearray()
    while value > 0x7F:
        output.append((value & 0x7F) | 0x80)
        value >>= 7
    output.append(value)
    return bytes(output)


def _fields(data: bytes):
    offset = 0
    while offset < len(data):
        key, offset = _read_varint(data, offset)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, offset = _read_varint(data, offset)
            yield number, wire, value
        elif wire == 2:
            length, offset = _read_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ValueError("truncated protobuf field")
            yield number, wire, data[offset:end]
            offset = end
        elif wire == 1:
            yield number, wire, data[offset : offset + 8]
            offset += 8
        elif wire == 5:
            yield number, wire, data[offset : offset + 4]
            offset += 4
        else:
            raise ValueError("unsupported protobuf wire type")


def _encode_field(number: int, wire: int, value: Any) -> bytes:
    key = _varint((number << 3) | wire)
    if wire == 0:
        return key + _varint(int(value))
    if wire == 2:
        raw = bytes(value)
        return key + _varint(len(raw)) + raw
    return key + bytes(value)


def _layer_name(layer: bytes) -> str:
    for number, wire, value in _fields(layer):
        if number == 1 and wire == 2:
            return bytes(value).decode("utf-8", "replace")
    return ""


def _merge_feature(feature: bytes, key_map: dict[int, int], value_map: dict[int, int]) -> bytes:
    result = bytearray()
    for number, wire, value in _fields(feature):
        if number == 2 and wire == 2:
            tags = []
            offset = 0
            raw = bytes(value)
            while offset < len(raw):
                item, offset = _read_varint(raw, offset)
                tags.append(item)
            remapped = bytearray()
            for index in range(0, len(tags) - 1, 2):
                remapped += _varint(key_map[tags[index]])
                remapped += _varint(value_map[tags[index + 1]])
            result += _encode_field(2, 2, remapped)
        else:
            result += _encode_field(number, wire, value)
    return bytes(result)


def _merge_layers(layers: list[bytes]) -> bytes:
    layers[0]
    keys: list[bytes] = []
    values: list[bytes] = []
    key_index: dict[bytes, int] = {}
    value_index: dict[bytes, int] = {}
    features: list[bytes] = []
    scalars: list[tuple[int, int, Any]] = []
    for layer_pos, layer in enumerate(layers):
        local_keys = [bytes(v) for n, w, v in _fields(layer) if n == 3 and w == 2]
        local_values = [bytes(v) for n, w, v in _fields(layer) if n == 4 and w == 2]
        km = {}
        vm = {}
        for i, item in enumerate(local_keys):
            if item not in key_index:
                key_index[item] = len(keys)
                keys.append(item)
            km[i] = key_index[item]
        for i, item in enumerate(local_values):
            if item not in value_index:
                value_index[item] = len(values)
                values.append(item)
            vm[i] = value_index[item]
        for n, w, value in _fields(layer):
            if n == 2 and w == 2:
                features.append(_merge_feature(bytes(value), km, vm))
            elif layer_pos == 0 and n not in {2, 3, 4}:
                scalars.append((n, w, value))
    result = bytearray()
    for n, w, value in scalars:
        result += _encode_field(n, w, value)
    for feature in features:
        result += _encode_field(2, 2, feature)
    for item in keys:
        result += _encode_field(3, 2, item)
    for item in values:
        result += _encode_field(4, 2, item)
    return bytes(result)


def _merge_vector_tiles(tiles: list[bytes]) -> bytes:
    if not tiles:
        return EMPTY_MVT
    if len(tiles) == 1:
        return tiles[0]
    grouped: dict[str, list[bytes]] = {}
    order: list[str] = []
    for tile in tiles:
        for number, wire, value in _fields(tile):
            if number != 3 or wire != 2:
                continue
            layer = bytes(value)
            name = _layer_name(layer)
            if name not in grouped:
                grouped[name] = []
                order.append(name)
            grouped[name].append(layer)
    output = bytearray()
    for name in order:
        output += _encode_field(3, 2, _merge_layers(grouped[name]))
    return bytes(output) or EMPTY_MVT


def _tile_bytes(packages: tuple[Any, ...], zoom: int, x: int, y: int) -> bytes:
    composite = len(packages) > 1
    tiles: list[bytes] = []
    for package in packages:
        if not _package_covers_tile(package, zoom, x, y, composite=composite):
            continue
        data = _tile_bytes_or_none(package, zoom, x, y)
        if data is not None:
            tiles.append(data)
    return _merge_vector_tiles(tiles)


class VectorMapLoopbackServer:
    """Own one same-origin HTTP endpoint for one installed map database."""

    def __init__(self, package: Any, asset_root: Path, document_factory: Any) -> None:
        packages = tuple(package) if isinstance(package, tuple | list) else (package,)
        from natureai_next.domain.maps import is_nautical_overlay

        self._packages = tuple(item for item in packages if not is_nautical_overlay(item))
        self._nautical_overlays = tuple(item for item in packages if is_nautical_overlay(item))
        self._asset_root = asset_root.resolve()
        self._token = secrets.token_urlsafe(24)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ApertureVectorMap/1"

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def do_GET(self) -> None:
                try:
                    parsed = urlparse(self.path)
                    prefix = f"/{owner._token}/"
                    if not parsed.path.startswith(prefix):
                        self.send_error(404)
                        return
                    relative = parsed.path[len(prefix) :]
                    if relative == "map.html":
                        body = document_factory(owner.base_url).encode("utf-8")
                        self._reply(200, b"text/html; charset=utf-8", body, no_store=True)
                        return
                    if relative.startswith("assets/"):
                        name = relative.removeprefix("assets/")
                        if name not in {"maplibre-gl.js", "maplibre-gl.css"}:
                            self.send_error(404)
                            return
                        path = (owner._asset_root / name).resolve()
                        if path.parent != owner._asset_root or not path.is_file():
                            self.send_error(404)
                            return
                        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                        self._reply(200, mime.encode("ascii"), path.read_bytes())
                        return
                    if relative.startswith("tile/") and relative.endswith(".pbf"):
                        parts = relative.split("/")
                        if len(parts) != 4:
                            raise ValueError("invalid tile path")
                        zoom = int(parts[1])
                        x = int(parts[2])
                        y = int(parts[3][:-4])
                        body = _tile_bytes(owner._packages, zoom, x, y)
                        self._reply(200, b"application/vnd.mapbox-vector-tile", body)
                        return
                    if relative.startswith("nautical/") and relative.endswith(".png"):
                        parts = relative.split("/")
                        if len(parts) != 5:
                            raise ValueError("invalid nautical overlay tile path")
                        overlay_index = int(parts[1])
                        zoom = int(parts[2])
                        x = int(parts[3])
                        y = int(parts[4][:-4])
                        package = owner._nautical_overlays[overlay_index]
                        body = _tile_bytes_or_none(package, zoom, x, y)
                        if body is None:
                            self.send_error(404)
                            return
                        content_type = (
                            b"image/webp"
                            if body.startswith(b"RIFF") and body[8:12] == b"WEBP"
                            else b"image/png"
                        )
                        self._reply(200, content_type, body)
                        return
                    self.send_error(404)
                except (ValueError, OSError, sqlite3.Error, gzip.BadGzipFile):
                    self.send_error(500)

            def _reply(
                self, status: int, content_type: bytes, body: bytes, *, no_store: bool = False
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type.decode("ascii"))
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header(
                    "Cache-Control",
                    "no-store" if no_store else "public, max-age=31536000, immutable",
                )
                self.end_headers()
                self.wfile.write(body)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="aperture-vector-map", daemon=True
        )
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}/{self._token}"

    @property
    def document_url(self) -> str:
        return self.base_url + "/map.html"

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
