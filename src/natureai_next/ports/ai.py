"""Stable ports for model execution, model storage, and vector search."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from natureai_next.domain.ai import EmbeddingVector, ProviderDiagnostics, SimilarityMatch


class AIExecutionProvider(Protocol):
    @property
    def identity(self) -> str: ...
    def diagnostics(self) -> ProviderDiagnostics: ...
    def load(self, artifact_path: Path, *, device: str, precision: str) -> object: ...
    def embed_images(
        self, model: object, images: Sequence[object]
    ) -> tuple[EmbeddingVector, ...]: ...
    def embed_text(self, model: object, texts: Sequence[str]) -> tuple[EmbeddingVector, ...]: ...
    def unload(self, model: object) -> None: ...
    def clear_device_cache(self) -> None: ...


class ImagePreprocessor(Protocol):
    @property
    def identity(self) -> str: ...
    def prepare(self, path: Path) -> object: ...


class AIEmbeddingRepository(Protocol):
    def store_embedding(
        self,
        *,
        asset_public_id: str,
        model_variant_id: int,
        preprocessing_identity: str,
        vector: EmbeddingVector,
        source_sha256: str | None,
        execution_provider: str,
        precision: str,
        application_version: str,
        inference_run_id: int | None = None,
    ) -> None: ...

    def exact_search(
        self,
        model_variant_id: int,
        preprocessing_identity: str,
        query: EmbeddingVector,
        limit: int = 50,
    ) -> tuple[SimilarityMatch, ...]: ...


class ComputeLeaseCoordinator(Protocol):
    def acquire(
        self,
        owner: str,
        *,
        exclusive: bool = True,
        timeout_seconds: float | None = None,
    ) -> AbstractContextManager[object]: ...


class AIRuntimeRepository(AIEmbeddingRepository, Protocol):
    def begin_inference_run(self, **values: object) -> int: ...
    def finish_inference_run(self, run_id: int, **values: object) -> None: ...
    def load_vectors(
        self, model_variant_id: int, preprocessing_identity: str
    ) -> dict[str, EmbeddingVector]: ...
    def register_index_generation(self, **values: object) -> int: ...
    def mark_index_corrupt(self, index_id: int, error: str) -> None: ...


class VectorIndexStore(Protocol):
    def build(
        self, directory: Path, *, generation: str, vectors: dict[str, EmbeddingVector]
    ) -> VectorIndex: ...
    def open(self, directory: Path) -> VectorIndex: ...


class VectorIndex(Protocol):
    @property
    def generation(self) -> str: ...
    def search(self, query: EmbeddingVector, limit: int) -> tuple[SimilarityMatch, ...]: ...
    def validate(self) -> bool: ...
