"""Stable imaging and metadata ports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ImageProbe:
    format_name: str
    mime_type: str
    pixel_width: int
    pixel_height: int
    frame_count: int
    orientation: int | None


@dataclass(frozen=True, slots=True)
class MetadataResult:
    normalized: Mapping[str, object]
    raw: Mapping[str, object]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RenderRequest:
    source: Path
    destination: Path
    max_width: int
    max_height: int
    quality: int
    output_format: str = "JPEG"


@dataclass(frozen=True, slots=True)
class RenderResult:
    pixel_width: int
    pixel_height: int
    output_size: int
    output_sha256: str


class ImageDecoder(Protocol):
    def probe(self, path: Path) -> ImageProbe: ...
    def render(self, request: RenderRequest) -> RenderResult: ...


class MetadataReader(Protocol):
    def read(self, path: Path) -> MetadataResult: ...
