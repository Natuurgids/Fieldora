"""Deterministic derivative cache keys, manifests, validation, and rebuild support."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from natureai_next.infrastructure.filesystem.atomic import atomic_write_bytes
from natureai_next.ports.media import ImageDecoder, RenderRequest


@dataclass(frozen=True, slots=True)
class DerivativeSpec:
    kind: str
    max_width: int
    max_height: int
    quality: int = 85
    output_format: str = "JPEG"


@dataclass(frozen=True, slots=True)
class DerivativeManifest:
    schema_version: int
    cache_key: str
    source_path: str
    source_size: int
    source_modified_at_ns: int
    source_sha256: str | None
    renderer_identity: str
    spec: DerivativeSpec
    output_sha256: str
    output_size: int
    pixel_width: int
    pixel_height: int


class DerivativeCache:
    def __init__(self, root: Path, decoder: ImageDecoder, renderer_identity: str) -> None:
        self.root = root
        self.decoder = decoder
        self.renderer_identity = renderer_identity

    def cache_key(
        self, source: Path, spec: DerivativeSpec, source_sha256: str | None = None
    ) -> str:
        stat = source.stat()
        payload = {
            "source_sha256": source_sha256,
            "source_size": stat.st_size,
            "source_modified_at_ns": stat.st_mtime_ns,
            "renderer": self.renderer_identity,
            "spec": asdict(spec),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def paths(self, key: str) -> tuple[Path, Path]:
        directory = self.root / key[:2] / key[2:4]
        return directory / f"{key}.jpg", directory / f"{key}.json"

    def get_or_create(
        self, source: Path, spec: DerivativeSpec, source_sha256: str | None = None
    ) -> tuple[Path, DerivativeManifest]:
        key = self.cache_key(source, spec, source_sha256)
        output, manifest_path = self.paths(key)
        existing = self._read_valid(output, manifest_path, key)
        if existing is not None:
            return output, existing
        result = self.decoder.render(
            RenderRequest(
                source, output, spec.max_width, spec.max_height, spec.quality, spec.output_format
            )
        )
        stat = source.stat()
        manifest = DerivativeManifest(
            1,
            key,
            str(source),
            stat.st_size,
            stat.st_mtime_ns,
            source_sha256,
            self.renderer_identity,
            spec,
            result.output_sha256,
            result.output_size,
            result.pixel_width,
            result.pixel_height,
        )
        atomic_write_bytes(
            manifest_path, (json.dumps(asdict(manifest), sort_keys=True, indent=2) + "\n").encode()
        )
        return output, manifest

    def invalidate(self, key: str) -> None:
        output, manifest = self.paths(key)
        output.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)

    def _read_valid(self, output: Path, manifest_path: Path, key: str) -> DerivativeManifest | None:
        if not output.is_file() or not manifest_path.is_file():
            return None
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw["spec"] = DerivativeSpec(**raw["spec"])
            manifest = DerivativeManifest(**raw)
            if manifest.cache_key != key or output.stat().st_size != manifest.output_size:
                return None
            if hashlib.sha256(output.read_bytes()).hexdigest() != manifest.output_sha256:
                return None
            return manifest
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
