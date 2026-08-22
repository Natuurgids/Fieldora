"""Persistent, orientation-correct thumbnail and preview rendering for the catalog UI."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Protocol

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from natureai_next.domain.importing import ImportSourceKind, classify_import_source
from natureai_next.infrastructure.filesystem.atomic import atomic_write_bytes


class RawThumbnailRenderer(Protocol):
    def render_jpeg(self, source: Path, max_size: int, quality: int) -> bytes | None: ...


class PillowCatalogThumbnailProvider:
    """Render and persist bounded JPEG derivatives without mutating source images.

    The cache identity includes the canonical source path, source size, source
    modification timestamp, requested maximum dimension, renderer identity, and
    output quality.  A compatible derivative is therefore reusable across
    application restarts while a changed source automatically receives a new key.
    """

    renderer_identity = "natureai.pillow.catalog.v1"

    def __init__(
        self,
        *,
        thumbnail_root: Path | None = None,
        preview_root: Path | None = None,
        library_root: Path | None = None,
        quality: int = 85,
        raw_renderer: RawThumbnailRenderer | None = None,
        background_workers: int | None = None,
    ) -> None:
        del background_workers
        if not 1 <= quality <= 100:
            raise ValueError("quality must be between 1 and 100")
        self._thumbnail_root = thumbnail_root
        self._preview_root = preview_root or thumbnail_root
        self._library_root = library_root
        self._quality = quality
        self._raw_renderer = raw_renderer
        self._locks_guard = Lock()
        self._locks: dict[str, Lock] = {}

    def load(
        self, *, source_path: Path | None, cached_path: Path | None, max_size: int
    ) -> bytes | None:
        """Read an Aperture-owned derivative only.

        Gallery and viewer callers never decode originals and never schedule work.
        Missing derivatives are produced by durable import/maintenance jobs.
        ``source_path`` is accepted for API compatibility but deliberately ignored.
        """
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        explicit_cache = self._resolve_explicit_cache(cached_path)
        if explicit_cache is not None:
            cached = self._read_valid_jpeg(explicit_cache, max_size)
            if cached is not None:
                return cached

        # Repair 2 generated thumbnails in the gallery worker and therefore always
        # displayed them, but it did not give every asset a stable Aperture-owned
        # cache location.  Keep that reliable worker-thread fallback while writing
        # the result once to the explicit per-asset cache path.  The Qt event loop
        # is never blocked and subsequent browsing (including offline browsing)
        # reads only the persisted JPEG.
        if source_path is None or not source_path.is_file():
            return None
        output = explicit_cache or self._cache_path_from_metadata(source_path, max_size)
        if output is None:
            return self._render(source_path, max_size)
        lock = self._lock_for(output.stem)
        with lock:
            cached = self._read_valid_jpeg(output, max_size)
            if cached is not None:
                return cached
            data = self._render(source_path, max_size)
            if data is not None:
                atomic_write_bytes(output, data)
            return data


    def asset_cache_path(self, public_id: str) -> Path | None:
        """Return the stable Aperture-owned thumbnail path for one catalog asset."""
        if self._thumbnail_root is None:
            return None
        key = hashlib.sha256(public_id.strip().encode("utf-8")).hexdigest()
        return self._thumbnail_root / "assets" / key[:2] / key[2:4] / f"{key}.jpg"

    def enqueue(self, *, source_path: Path, max_size: int) -> bool:
        """Deprecated guard: UI-driven generation is forbidden in Build 29."""
        del source_path, max_size
        return False

    def materialize(self, *, source_path: Path, max_size: int) -> bytes | None:
        """Generate and atomically persist one derivative; safe to retry after interruption."""
        if not source_path.is_file():
            return None
        cache_path = self._cache_path(source_path, max_size)
        if cache_path is None:
            return self._render(source_path, max_size)
        lock = self._lock_for(cache_path.stem)
        try:
            with lock:
                data = self._read_valid_jpeg(cache_path, max_size)
                if data is not None:
                    return data
                data = self._render(source_path, max_size)
                if data is not None:
                    atomic_write_bytes(cache_path, data)
                return data
        finally:
            with self._locks_guard:
                if not lock.locked():
                    self._locks.pop(cache_path.stem, None)

    def cache_path(self, *, source_path: Path, max_size: int) -> Path | None:
        return self._cache_path_from_metadata(source_path, max_size)

    def close(self, *, wait: bool = True) -> None:
        """No-op: Build 29 owns workers in the durable JobEngine."""
        del wait

    def _resolve_explicit_cache(self, path: Path | None) -> Path | None:
        if path is None:
            return None
        if path.is_absolute():
            return path
        if self._library_root is not None:
            return self._library_root / path
        return None

    def _cache_path_from_metadata(self, source: Path, max_size: int) -> Path | None:
        try:
            return self._cache_path(source, max_size)
        except (FileNotFoundError, PermissionError, OSError):
            return None

    def _cache_path(self, source: Path, max_size: int) -> Path | None:
        root = self._preview_root if max_size > 384 else self._thumbnail_root
        if root is None:
            return None
        stat = source.stat()
        payload = {
            "source": str(source.resolve()).casefold(),
            "source_size": stat.st_size,
            "source_mtime_ns": stat.st_mtime_ns,
            "max_size": max_size,
            "quality": self._quality,
            "renderer": self.renderer_identity,
        }
        key = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return root / key[:2] / key[2:4] / f"{key}.jpg"

    def _render(self, source: Path, max_size: int) -> bytes | None:
        if (
            classify_import_source(source) is ImportSourceKind.RAW_PHOTO
            and self._raw_renderer is not None
        ):
            return self._raw_renderer.render_jpeg(source, max_size, self._quality)
        try:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened)
                image = _to_srgb(image)
                if image.mode != "RGB":
                    image = image.convert("RGB")
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                output = BytesIO()
                image.save(output, format="JPEG", quality=self._quality, optimize=True)
                return output.getvalue()
        except (OSError, UnidentifiedImageError, ValueError):
            return None

    @staticmethod
    def _read_valid_jpeg(path: Path, max_size: int) -> bytes | None:
        if not path.is_file():
            return None
        try:
            data = path.read_bytes()
            with Image.open(BytesIO(data)) as image:
                if image.format != "JPEG":
                    return None
                # A persisted thumbnail may be larger than the current widget request.
                # Qt scales the decoded pixmap for display; rejecting a 384px derivative
                # for a 192px gallery cell made every valid thumbnail appear missing.
                image.verify()
            return data
        except (OSError, UnidentifiedImageError, ValueError):
            return None

    def _lock_for(self, key: str) -> Lock:
        with self._locks_guard:
            return self._locks.setdefault(key, Lock())


def _to_srgb(image: Image.Image) -> Image.Image:
    profile = image.info.get("icc_profile")
    if not profile:
        return image
    try:
        source_profile = ImageCms.ImageCmsProfile(BytesIO(profile))
        target_profile = ImageCms.createProfile("sRGB")
        output_mode = "RGB" if image.mode not in {"RGB", "RGBA"} else image.mode
        return ImageCms.profileToProfile(
            image, source_profile, target_profile, outputMode=output_mode
        )
    except (OSError, TypeError, ValueError, ImageCms.PyCMSError):
        return image
