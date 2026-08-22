"""Application services for local model diagnostics, embeddings, and similarity."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from natureai_next import __version__
from natureai_next.domain.ai import EmbeddingVector, ProviderDiagnostics, SimilarityMatch
from natureai_next.ports.ai import (
    AIEmbeddingRepository,
    AIExecutionProvider,
    ComputeLeaseCoordinator,
    ImagePreprocessor,
)


@dataclass(frozen=True, slots=True)
class EmbeddingItem:
    asset_public_id: str
    image_path: Path
    source_sha256: str | None


@dataclass(frozen=True, slots=True)
class EmbeddingBatchResult:
    completed: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]
    final_batch_size: int
    retries: int


class AIEmbeddingService:
    def __init__(
        self,
        repository: AIEmbeddingRepository,
        provider: AIExecutionProvider,
        preprocessor: ImagePreprocessor,
        gpu: ComputeLeaseCoordinator,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._preprocessor = preprocessor
        self._gpu = gpu

    def embed_images(
        self,
        *,
        model: object,
        model_variant_id: int,
        precision: str,
        items: Sequence[EmbeddingItem],
        initial_batch_size: int,
        cancellation_check: Callable[[], None] = lambda: None,
        device: str = "cuda",
        inference_run_id: int | None = None,
    ) -> EmbeddingBatchResult:
        completed: list[str] = []
        failed: list[tuple[str, str]] = []
        retries = 0
        batch_size = initial_batch_size
        index = 0
        while index < len(items):
            cancellation_check()
            current_items = items[index : index + batch_size]
            prepared: list[object] = []
            accepted: list[EmbeddingItem] = []
            for item in current_items:
                try:
                    cancellation_check()
                    prepared.append(self._preprocessor.prepare(item.image_path))
                    accepted.append(item)
                except Exception as exc:
                    failed.append((item.asset_public_id, str(exc)))
            if not prepared:
                index += len(current_items)
                continue
            try:
                lease_context = (
                    self._gpu.acquire("embedding-batch", exclusive=True)
                    if device == "cuda"
                    else _null_context()
                )
                with lease_context:
                    vectors = self._provider.embed_images(model, prepared)
                if len(vectors) != len(accepted):
                    raise RuntimeError("provider returned an unexpected number of embeddings")
                for item, vector in zip(accepted, vectors, strict=True):
                    self._repository.store_embedding(
                        asset_public_id=item.asset_public_id,
                        model_variant_id=model_variant_id,
                        preprocessing_identity=self._preprocessor.identity,
                        vector=vector,
                        source_sha256=item.source_sha256,
                        execution_provider=f"{self._provider.identity}:{device}",
                        precision=precision,
                        application_version=__version__,
                        inference_run_id=inference_run_id,
                    )
                    completed.append(item.asset_public_id)
                index += len(current_items)
            except Exception as exc:
                if device == "cuda" and _is_out_of_memory(exc) and batch_size > 1:
                    self._provider.clear_device_cache()
                    batch_size = max(1, batch_size // 2)
                    retries += 1
                    continue
                for item in accepted:
                    failed.append((item.asset_public_id, str(exc)))
                index += len(current_items)
        return EmbeddingBatchResult(tuple(completed), tuple(failed), batch_size, retries)

    def embed_text(self, model: object, texts: Sequence[str]) -> tuple[EmbeddingVector, ...]:
        return self._provider.embed_text(model, texts)


class AISearchService:
    def __init__(self, repository: AIEmbeddingRepository) -> None:
        self._repository = repository

    def exact(
        self,
        model_variant_id: int,
        preprocessing_identity: str,
        query: EmbeddingVector,
        limit: int = 50,
    ) -> tuple[SimilarityMatch, ...]:
        return self._repository.exact_search(model_variant_id, preprocessing_identity, query, limit)


class AIDiagnosticsService:
    def __init__(self, providers: Sequence[AIExecutionProvider]) -> None:
        self._providers = tuple(providers)

    def inspect(self) -> tuple[ProviderDiagnostics, ...]:
        return tuple(provider.diagnostics() for provider in self._providers)

    def as_json(self) -> str:
        return json.dumps(
            [asdict(diagnostic) for diagnostic in self.inspect()], sort_keys=True, default=str
        )


class _null_context:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def _is_out_of_memory(exc: Exception) -> bool:
    text = str(exc).lower()
    return "out of memory" in text or "cuda oom" in text
