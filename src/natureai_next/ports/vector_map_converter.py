"""Port for converting verified OSM extracts into Aperture street packages."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol


class VectorConversionResult(Protocol):
    path: Path
    sha256: str
    size_bytes: int
    min_zoom: int
    max_zoom: int


class VectorMapConverter(Protocol):
    def convert(
        self,
        source: Path,
        destination: Path,
        entry: object,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> VectorConversionResult: ...
