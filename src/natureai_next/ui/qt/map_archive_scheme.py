"""Qt WebEngine adapter for catalog-authorized local vector MBTiles."""

from __future__ import annotations

import base64
import contextlib
import gzip
import zlib
from typing import Any

from natureai_next.infrastructure.subsystems.map_archive import CatalogVectorTileReader

SCHEME_NAME = b"aperture-map"


def package_authority(package_public_id: str) -> str:
    if not package_public_id or len(package_public_id) > 120:
        raise ValueError("invalid map package public ID")
    encoded = base64.b32encode(package_public_id.encode("utf-8")).decode("ascii")
    token = encoded.rstrip("=").lower()
    return "id-" + ".".join(token[index : index + 50] for index in range(0, len(token), 50))


def package_id_from_scheme_url(scheme: str, host: str, path: str) -> str:
    if scheme != SCHEME_NAME.decode("ascii") or not path.startswith("/tile/"):
        raise ValueError("invalid Aperture vector-tile URL")
    authority = host.strip().casefold()
    if not authority.startswith("id-"):
        raise ValueError("invalid map package public ID")
    labels = authority.removeprefix("id-").split(".")
    if (
        not labels
        or any(not label or len(label) > 50 for label in labels)
        or any(
            character not in "abcdefghijklmnopqrstuvwxyz234567"
            for label in labels
            for character in label
        )
    ):
        raise ValueError("invalid map package public ID")
    token = "".join(labels)
    padding = "=" * ((8 - len(token) % 8) % 8)
    try:
        package_id = base64.b32decode((token.upper() + padding).encode("ascii")).decode("utf-8")
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid map package public ID") from exc
    if package_authority(package_id) != authority:
        raise ValueError("invalid map package public ID")
    return package_id


def register_aperture_map_scheme() -> None:
    from PySide6.QtWebEngineCore import QWebEngineUrlScheme

    if QWebEngineUrlScheme.schemeByName(SCHEME_NAME).name():
        return
    scheme = QWebEngineUrlScheme(SCHEME_NAME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.LocalScheme
        | QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.CorsEnabled
        | QWebEngineUrlScheme.Flag.FetchApiAllowed
    )
    QWebEngineUrlScheme.registerScheme(scheme)


def create_map_archive_scheme_handler(reader: CatalogVectorTileReader, parent: Any = None) -> Any:
    """Serve complete z/x/y vector tiles from a read-only MBTiles database."""
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtWebEngineCore import QWebEngineUrlRequestJob, QWebEngineUrlSchemeHandler

    class _VectorTileSchemeHandler(QWebEngineUrlSchemeHandler):
        def __init__(self, owner: Any = None) -> None:
            super().__init__(owner)
            self._buffers: set[Any] = set()

        def requestStarted(self, job: Any) -> None:
            try:
                if bytes(job.requestMethod()).upper() != b"GET":
                    job.fail(QWebEngineUrlRequestJob.Error.RequestDenied)
                    return
                url = job.requestUrl()
                package_id = package_id_from_scheme_url(url.scheme(), url.host(), url.path())
                parts = url.path().split("/")
                if len(parts) != 5 or parts[1] != "tile" or not parts[4].endswith(".pbf"):
                    raise ValueError("invalid vector-tile request")
                zoom = int(parts[2])
                x = int(parts[3])
                y = int(parts[4][:-4])
                data = reader.read_tile(package_id, zoom, x, y)
                if data is None:
                    # A zero-byte body is rejected by some MapLibre worker builds.
                    # Return a syntactically valid MVT containing one empty layer.
                    data = b"\x1a\x0d\x0a\x06_empty\x28\x80\x20\x78\x02"
                # Planetiler stores MVT payloads gzip-compressed in MBTiles. Qt
                # custom-scheme replies do not consistently apply Content-Encoding
                # before MapLibre's protobuf decoder, so decode them here and return
                # plain MVT bytes.
                if data[:2] == b"\x1f\x8b":
                    data = gzip.decompress(data)
                elif len(data) >= 2 and data[0] == 0x78:
                    # Some MBTiles producers use zlib-wrapped MVT payloads.
                    with contextlib.suppress(zlib.error):
                        data = zlib.decompress(data)
                if not data:
                    data = b"\x1a\x0d\x0a\x06_empty\x28\x80\x20\x78\x02"
                job.setAdditionalResponseHeaders(
                    {
                        b"Content-Length": str(len(data)).encode("ascii"),
                        b"Cache-Control": b"public, max-age=31536000, immutable",
                        b"Access-Control-Allow-Origin": b"*",
                    }
                )
                buffer = QBuffer(job)
                buffer.setData(data)
                if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
                    raise OSError("vector tile reply buffer could not be opened")
                self._buffers.add(buffer)
                buffer.destroyed.connect(lambda *_: self._buffers.discard(buffer))
                job.reply(b"application/x-protobuf", buffer)
            except (UnicodeError, ValueError, KeyError, FileNotFoundError):
                job.fail(QWebEngineUrlRequestJob.Error.UrlInvalid)
            except Exception:
                job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)

    return _VectorTileSchemeHandler(parent)


def install_map_archive_scheme_handler(profile: Any, handler: Any) -> None:
    profile.installUrlSchemeHandler(SCHEME_NAME, handler)
