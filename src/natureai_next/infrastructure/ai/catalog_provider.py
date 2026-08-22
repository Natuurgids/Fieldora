"""AIExecutionProvider adapter selected by catalog string key."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from natureai_next.domain.ai import EmbeddingVector, ProviderDiagnostics
from natureai_next.infrastructure.ai.dynamic_model_manager import DynamicModelManager


class CatalogAIExecutionProvider:
    def __init__(self, manager: DynamicModelManager, key: str | None = None) -> None:
        self.manager = manager
        self.key = key

    @property
    def identity(self) -> str:
        return str(getattr(self._provider(), "identity", self.key or self.manager.active_key))

    def diagnostics(self) -> ProviderDiagnostics:
        missing = self.manager.missing_dependencies(self.key or self.manager.active_key)
        if missing:
            return ProviderDiagnostics(
                provider=self.key or self.manager.active_key,
                available=False,
                torch_version=None,
                cuda_runtime=None,
                device_name=None,
                compute_capability=None,
                total_memory_bytes=None,
                detail="Missing optional dependencies: " + ", ".join(missing),
            )
        return self._provider().diagnostics()

    def load(self, artifact_path: Path, *, device: str, precision: str) -> object:
        return self._provider().load(artifact_path, device=device, precision=precision)

    def embed_images(self, model: object, images: Sequence[object]) -> tuple[EmbeddingVector, ...]:
        return self._provider().embed_images(model, images)

    def embed_text(self, model: object, texts: Sequence[str]) -> tuple[EmbeddingVector, ...]:
        return self._provider().embed_text(model, texts)

    def unload(self, model: object) -> None:
        self._provider().unload(model)

    def clear_device_cache(self) -> None:
        self._provider().clear_device_cache()

    def _provider(self):
        return self.manager.provider(self.key)
