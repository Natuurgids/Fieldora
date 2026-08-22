"""Production AI orchestration for inference provenance and resilient vector search."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from natureai_next import __version__
from natureai_next.application.ai import AIEmbeddingService, EmbeddingBatchResult, EmbeddingItem
from natureai_next.domain.ai import EmbeddingVector, SimilarityMatch
from natureai_next.ports.ai import AIRuntimeRepository, VectorIndexStore


@dataclass(frozen=True, slots=True)
class IndexBuildResult:
    index_id: int
    generation: str
    source_row_count: int
    directory: Path


class InferenceRunService:
    def __init__(self, repository: AIRuntimeRepository, embeddings: AIEmbeddingService) -> None:
        self._repository = repository
        self._embeddings = embeddings

    def embed_images(
        self,
        *,
        model: object,
        model_variant_id: int,
        precision: str,
        items: Sequence[EmbeddingItem],
        initial_batch_size: int,
        execution_provider: str,
        job_public_id: str | None = None,
        cancellation_check: Callable[[], None] = lambda: None,
        device: str = "cuda",
    ) -> EmbeddingBatchResult:
        run_id = self._repository.begin_inference_run(
            public_id=str(uuid.uuid4()),
            model_variant_id=model_variant_id,
            execution_provider=execution_provider,
            precision=precision,
            application_version=__version__,
            requested_item_count=len(items),
            parameters_json=json.dumps(
                {"device": device, "initial_batch_size": initial_batch_size}, sort_keys=True
            ),
            job_public_id=job_public_id,
        )
        try:
            result = self._embeddings.embed_images(
                model=model,
                model_variant_id=model_variant_id,
                precision=precision,
                items=items,
                initial_batch_size=initial_batch_size,
                cancellation_check=cancellation_check,
                device=device,
                inference_run_id=run_id,
            )
            self._repository.finish_inference_run(
                run_id,
                completed=len(result.completed),
                failed=len(result.failed),
                retries=result.retries,
                final_batch_size=result.final_batch_size,
            )
            return result
        except Exception as exc:
            self._repository.finish_inference_run(
                run_id,
                completed=0,
                failed=len(items),
                retries=0,
                final_batch_size=initial_batch_size,
                error_text=str(exc),
            )
            raise


class VectorIndexService:
    def __init__(
        self, repository: AIRuntimeRepository, root: Path, indexes: VectorIndexStore
    ) -> None:
        self._repository = repository
        self._root = root
        self._indexes = indexes

    def rebuild(self, model_variant_id: int, preprocessing_identity: str) -> IndexBuildResult:
        vectors = self._repository.load_vectors(model_variant_id, preprocessing_identity)
        if not vectors:
            raise ValueError("no valid embeddings are available for indexing")
        generation = uuid.uuid4().hex
        directory = self._root / str(model_variant_id) / preprocessing_identity / generation
        self._indexes.build(directory, generation=generation, vectors=vectors)
        manifest_path = directory / "manifest.json"
        manifest_json = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(manifest_json)
        index_id = self._repository.register_index_generation(
            public_id=str(uuid.uuid4()),
            model_variant_id=model_variant_id,
            preprocessing_identity=preprocessing_identity,
            generation=generation,
            path_token=str(directory),
            manifest_json=manifest_json,
            checksum=str(manifest["checksum"]),
            source_row_count=len(vectors),
            backend="local_exact",
        )
        return IndexBuildResult(index_id, generation, len(vectors), directory)

    def search_with_fallback(
        self,
        *,
        index_id: int,
        directory: Path,
        model_variant_id: int,
        preprocessing_identity: str,
        query: EmbeddingVector,
        limit: int = 50,
    ) -> tuple[SimilarityMatch, ...]:
        try:
            index = self._indexes.open(directory)
            if not index.validate():
                raise ValueError("vector index validation failed")
            return index.search(query, limit)
        except Exception as exc:
            self._repository.mark_index_corrupt(index_id, str(exc))
            return self._repository.exact_search(
                model_variant_id, preprocessing_identity, query, limit
            )

    def parity(self, model_variant_id: int, preprocessing_identity: str, directory: Path) -> bool:
        vectors = self._repository.load_vectors(model_variant_id, preprocessing_identity)
        try:
            index = self._indexes.open(directory)
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            return index.validate() and int(manifest["count"]) == len(vectors)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return False
