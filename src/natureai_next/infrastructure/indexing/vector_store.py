"""Adapter exposing the local checksummed vector index through its port."""

from __future__ import annotations

from pathlib import Path

from natureai_next.domain.ai import EmbeddingVector
from natureai_next.infrastructure.indexing.vector import LocalVectorIndex, LocalVectorIndexBuilder


class LocalVectorIndexStore:
    def __init__(self) -> None:
        self._builder = LocalVectorIndexBuilder()

    def build(self, directory: Path, *, generation: str, vectors: dict[str, EmbeddingVector]):
        return self._builder.build(directory, generation=generation, vectors=vectors)

    def open(self, directory: Path):
        return LocalVectorIndex(directory)
