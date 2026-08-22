"""Durable AI job handlers integrated with the persistent job engine."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from natureai_next.application.ai import EmbeddingItem
from natureai_next.application.ai_review import TaxonomyTextEmbeddingService
from natureai_next.application.ai_runtime import InferenceRunService, VectorIndexService
from natureai_next.ports.jobs import JobExecutionContext


@dataclass(frozen=True, slots=True)
class LoadedModel:
    model: object
    model_variant_id: int
    precision: str
    provider_identity: str
    device: str


class EmbeddingJobHandler:
    job_type = "ai.embed_images.v1"
    resource_class = "gpu"

    def __init__(
        self, service: InferenceRunService, model_loader: Callable[[dict[str, object]], LoadedModel]
    ) -> None:
        self._service = service
        self._model_loader = model_loader

    def execute(self, context: JobExecutionContext) -> dict[str, object]:
        payload = json.loads(context.job.payload_json)
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported embedding job payload")
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise ValueError("embedding job items must be a list")
        items = tuple(
            EmbeddingItem(
                str(item["asset_public_id"]),
                Path(str(item["image_path"])),
                item.get("source_sha256"),
            )
            for item in raw_items
        )
        loaded = self._model_loader(payload)
        context.report_progress(0, len(items), "assets", "Embedding images")
        result = self._service.embed_images(
            model=loaded.model,
            model_variant_id=loaded.model_variant_id,
            precision=loaded.precision,
            items=items,
            initial_batch_size=max(1, int(payload.get("initial_batch_size", 8))),
            execution_provider=loaded.provider_identity,
            job_public_id=context.job.public_id,
            cancellation_check=context.cancellation.raise_if_cancelled,
            device=loaded.device,
        )
        context.report_progress(
            len(result.completed) + len(result.failed), len(items), "assets", "Embedding complete"
        )
        return {
            "completed": len(result.completed),
            "failed": len(result.failed),
            "retries": result.retries,
            "final_batch_size": result.final_batch_size,
        }


class VectorIndexRebuildJobHandler:
    job_type = "ai.rebuild_vector_index.v1"
    resource_class = "cpu"

    def __init__(self, service: VectorIndexService) -> None:
        self._service = service

    def execute(self, context: JobExecutionContext) -> dict[str, object]:
        payload = json.loads(context.job.payload_json)
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported vector-index job payload")
        context.cancellation.raise_if_cancelled()
        result = self._service.rebuild(
            int(payload["model_variant_id"]), str(payload["preprocessing_identity"])
        )
        context.report_progress(1, 1, "index", "Vector index activated")
        return {
            "index_id": result.index_id,
            "generation": result.generation,
            "source_row_count": result.source_row_count,
        }


class SuggestionGenerationJobHandler:
    """Durable per-asset suggestion generation with resumable item progress."""

    job_type = "ai.generate_suggestions.v1"
    resource_class = "gpu"

    def __init__(
        self, generate_asset: Callable[[dict[str, object], JobExecutionContext], int]
    ) -> None:
        self._generate_asset = generate_asset

    def execute(self, context: JobExecutionContext) -> dict[str, object]:
        payload = json.loads(context.job.payload_json)
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported suggestion generation payload")
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("suggestion generation items must be a list")
        completed = 0
        processed = 0
        failed: list[dict[str, str]] = []
        context.report_progress(0, len(items), "assets", "Generating AI suggestions")
        for raw in items:
            context.cancellation.raise_if_cancelled()
            if not isinstance(raw, dict) or "asset_public_id" not in raw:
                raise ValueError("invalid suggestion generation item")
            try:
                completed += self._generate_asset(dict(raw), context)
            except Exception as exc:
                failed.append({"asset_public_id": str(raw["asset_public_id"]), "error": str(exc)})
            processed += 1
            context.report_progress(
                processed,
                len(items),
                "assets",
                "Generating AI suggestions",
            )
        return {"completed": completed, "failed": failed}


class TaxonomyTextEmbeddingJobHandler:
    job_type = "ai.embed_taxonomy_text.v1"
    resource_class = "gpu"

    def __init__(
        self,
        service_factory: Callable[[dict[str, object]], TaxonomyTextEmbeddingService],
    ) -> None:
        self._service_factory = service_factory

    def execute(self, context: JobExecutionContext) -> dict[str, object]:
        payload = json.loads(context.job.payload_json)
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported taxonomy embedding job payload")
        model_variant_id = int(payload["model_variant_id"])
        preprocessing_identity = str(payload["preprocessing_identity"])
        language_tags = tuple(str(value) for value in payload.get("language_tags", ()))
        region_codes = tuple(str(value) for value in payload.get("region_codes", ()))
        service = self._service_factory(payload)
        result = service.rebuild(
            model_variant_id=model_variant_id,
            preprocessing_identity=preprocessing_identity,
            prompt_set_public_id=(
                None
                if payload.get("prompt_set_public_id") is None
                else str(payload["prompt_set_public_id"])
            ),
            now_us=int(payload["now_us"]),
            language_tags=language_tags,
            region_codes=region_codes,
            include_synonyms=bool(payload.get("include_synonyms", True)),
            batch_size=int(payload.get("batch_size", 128)),
            cancellation_check=context.cancellation.raise_if_cancelled,
            progress=lambda current, total: context.report_progress(
                current, total, "labels", "Embedding taxonomy labels"
            ),
        )
        return {
            "labels_seen": result.labels_seen,
            "embeddings_written": result.embeddings_written,
            "batches": result.batches,
        }
