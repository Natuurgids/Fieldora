"""Pillow-backed format probing and orientation-correct derivative rendering."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image, ImageOps, UnidentifiedImageError

from natureai_next.ports.media import ImageProbe, RenderRequest, RenderResult


class ImageDecodeError(ValueError):
    """The source is not a supported, decodable image."""


class PillowImageDecoder:
    renderer_identity = f"pillow:{Image.__version__}"

    def probe(self, path: Path) -> ImageProbe:
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                fmt = image.format or "UNKNOWN"
                mime = Image.MIME.get(fmt, "application/octet-stream")
                orientation = image.getexif().get(274)
                return ImageProbe(
                    fmt, mime, image.width, image.height, getattr(image, "n_frames", 1), orientation
                )
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            raise ImageDecodeError(f"cannot decode image: {path}") from exc

    def render(self, request: RenderRequest) -> RenderResult:
        if request.max_width <= 0 or request.max_height <= 0:
            raise ValueError("render dimensions must be positive")
        request.destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(request.source) as opened:
                image = ImageOps.exif_transpose(opened)
                if image.mode not in {"RGB", "L"}:
                    image = image.convert("RGB")
                image.thumbnail((request.max_width, request.max_height), Image.Resampling.LANCZOS)
                with NamedTemporaryFile(
                    dir=request.destination.parent,
                    prefix=f".{request.destination.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temp:
                    temp_path = Path(temp.name)
                try:
                    image.save(
                        temp_path,
                        format=request.output_format,
                        quality=request.quality,
                        optimize=True,
                    )
                    # Windows requires a writable handle for FlushFileBuffers,
                    # which backs os.fsync(). Opening the completed temporary
                    # image read-only causes every otherwise successful render
                    # to be reported as ImageDecodeError on Windows.
                    with temp_path.open("rb+") as stream:
                        stream.flush()
                        os.fsync(stream.fileno())
                    digest = hashlib.sha256(temp_path.read_bytes()).hexdigest()
                    size = temp_path.stat().st_size
                    os.replace(temp_path, request.destination)
                    return RenderResult(image.width, image.height, size, digest)
                finally:
                    temp_path.unlink(missing_ok=True)
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            raise ImageDecodeError(f"cannot render image: {request.source}") from exc
