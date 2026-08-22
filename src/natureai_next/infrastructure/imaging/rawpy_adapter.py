"""LibRaw-backed camera RAW decoding behind existing media ports."""

from __future__ import annotations

import hashlib
import os
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image

from natureai_next.domain.importing import ImportSourceKind, classify_import_source
from natureai_next.infrastructure.imaging.pillow_adapter import ImageDecodeError
from natureai_next.ports.media import (
    ImageDecoder,
    ImageProbe,
    MetadataReader,
    MetadataResult,
    RenderRequest,
    RenderResult,
)


def _rawpy():
    try:
        import rawpy
    except ImportError as exc:
        raise ImageDecodeError("camera RAW support is not installed") from exc
    return rawpy


class RawPyImageDecoder:
    renderer_identity = "rawpy:libraw"

    def probe(self, path: Path) -> ImageProbe:
        try:
            with _rawpy().imread(str(path)) as raw:
                sizes = raw.sizes
                width = int(sizes.width or sizes.raw_width)
                height = int(sizes.height or sizes.raw_height)
                if width <= 0 or height <= 0:
                    raise ValueError("RAW dimensions are unavailable")
                return ImageProbe(
                    path.suffix.lstrip(".").upper(), "image/x-camera-raw", width, height, 1, None
                )
        except ImageDecodeError:
            raise
        except Exception as exc:
            raise ImageDecodeError(f"cannot decode camera RAW: {path}") from exc

    def render(self, request: RenderRequest) -> RenderResult:
        try:
            with _rawpy().imread(str(request.source)) as raw:
                pixels = raw.postprocess(use_camera_wb=True, output_bps=8, half_size=True)
            image = Image.fromarray(pixels)
            image.thumbnail((request.max_width, request.max_height), Image.Resampling.LANCZOS)
            request.destination.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(
                dir=request.destination.parent,
                prefix=f".{request.destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp:
                temp_path = Path(temp.name)
            try:
                image.save(
                    temp_path, format=request.output_format, quality=request.quality, optimize=True
                )
                digest = hashlib.sha256(temp_path.read_bytes()).hexdigest()
                size = temp_path.stat().st_size
                os.replace(temp_path, request.destination)
                return RenderResult(image.width, image.height, size, digest)
            finally:
                temp_path.unlink(missing_ok=True)
        except ImageDecodeError:
            raise
        except Exception as exc:
            raise ImageDecodeError(f"cannot render camera RAW: {request.source}") from exc


class RawPyMetadataReader:
    def read(self, path: Path) -> MetadataResult:
        probe = RawPyImageDecoder().probe(path)
        normalized = {
            "pixel_width": probe.pixel_width,
            "pixel_height": probe.pixel_height,
            "format_name": probe.format_name,
        }
        return MetadataResult(
            normalized,
            {"decoder": "LibRaw", "format_name": probe.format_name},
            ("raw_metadata_limited",),
        )


class HybridImageDecoder:
    def __init__(self, primary: ImageDecoder, raw: ImageDecoder) -> None:
        self._primary, self._raw = primary, raw

    def probe(self, path: Path) -> ImageProbe:
        if classify_import_source(path) is ImportSourceKind.RAW_PHOTO:
            return self._raw.probe(path)
        return self._primary.probe(path)

    def render(self, request: RenderRequest) -> RenderResult:
        if classify_import_source(request.source) is ImportSourceKind.RAW_PHOTO:
            return self._raw.render(request)
        return self._primary.render(request)


class HybridMetadataReader:
    def __init__(self, primary: MetadataReader, raw: MetadataReader) -> None:
        self._primary, self._raw = primary, raw

    def read(self, path: Path) -> MetadataResult:
        if classify_import_source(path) is ImportSourceKind.RAW_PHOTO:
            return self._raw.read(path)
        return self._primary.read(path)


class RawPyThumbnailRenderer:
    def render_jpeg(self, source: Path, max_size: int, quality: int) -> bytes | None:
        try:
            with _rawpy().imread(str(source)) as raw:
                pixels = raw.postprocess(use_camera_wb=True, output_bps=8, half_size=True)
            image = Image.fromarray(pixels)
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="JPEG", quality=quality, optimize=True)
            return output.getvalue()
        except Exception:
            return None
