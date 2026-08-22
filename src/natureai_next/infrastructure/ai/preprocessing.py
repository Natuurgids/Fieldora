"""Versioned BioCLIP-compatible image preprocessing."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


class BioClipImagePreprocessor:
    def __init__(self, input_size: int, identity: str) -> None:
        if input_size < 32 or input_size > 4096:
            raise ValueError("invalid model input size")
        if not identity:
            raise ValueError("preprocessing identity is required")
        self._size = input_size
        self._identity = identity

    @property
    def identity(self) -> str:
        return self._identity

    def prepare(self, path: Path) -> object:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            width, height = image.size
            edge = min(width, height)
            left = (width - edge) // 2
            top = (height - edge) // 2
            cropped = image.crop((left, top, left + edge, top + edge))
            return cropped.resize((self._size, self._size), Image.Resampling.BICUBIC).copy()
