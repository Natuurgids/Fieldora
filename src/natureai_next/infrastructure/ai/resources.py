"""Infrastructure backend for local AI resource operations."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from natureai_next.application.ai_review import PromptSetService, TaxonomyTextEmbeddingService
from natureai_next.infrastructure.ai.openclip_provider import OpenClipExecutionProvider
from natureai_next.infrastructure.ai.package import ModelPackageInstaller, ModelPackageVerifier
from natureai_next.infrastructure.ai.prompts import (
    load_prompt_set,
    prompt_set_checksum,
    validate_prompt_set,
)
from natureai_next.infrastructure.database.ai_generation import (
    SqliteTaxonomyEmbeddingRefreshPlanSource,
    SqliteTaxonomyEmbeddingStore,
    SqliteTaxonomyLabelSource,
)
from natureai_next.infrastructure.database.ai_review import SqlitePromptSetStore
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.taxonomy import SqliteTaxonomyAdapter
from natureai_next.infrastructure.taxonomy.package import Ed25519TaxonomyPackageVerifier


class LocalAIResourceBackend:
    def __init__(
        self,
        *,
        factory: SqliteConnectionFactory,
        models_root: Path,
        id_factory: Callable[[], str],
        now_us: Callable[[], int],
    ) -> None:
        self._factory = factory
        self._models_root = models_root
        self._id_factory = id_factory
        self._now_us = now_us

    def install_model(self, package_path: Path, trusted_keys: dict[str, bytes]) -> str:
        return ModelPackageInstaller(
            self._factory, self._models_root, ModelPackageVerifier(trusted_keys)
        ).install(package_path, activate=True)

    def install_prompt_set(self, manifest_path: Path, *, model_family: str | None = None) -> str:
        record = PromptSetService(
            SqlitePromptSetStore(self._factory),
            loader=load_prompt_set,
            checksum=prompt_set_checksum,
            validator=validate_prompt_set,
        ).install(
            manifest_path,
            public_id=self._id_factory(),
            now_us=self._now_us(),
            activate=True,
            model_family=model_family,
        )
        return record.public_id

    def install_taxonomy(self, package_path: Path, trusted_keys: dict[str, bytes]) -> str:
        package = Ed25519TaxonomyPackageVerifier(trusted_keys).verify(package_path)
        return SqliteTaxonomyAdapter(self._factory).install(package, now_us=self._now_us())

    def build_taxonomy_embeddings(self) -> tuple[int, int]:
        plans = SqliteTaxonomyEmbeddingRefreshPlanSource(self._factory).active_plans()
        if not plans:
            raise RuntimeError("No active model variant is available.")
        provider = OpenClipExecutionProvider()
        total_labels = total_written = 0
        for plan in plans:
            connection = self._factory.connect(read_only=True)
            try:
                row = connection.execute(
                    "SELECT p.install_path_token,v.artifact_relative_path,v.precision,v.device_requirements_json FROM model_variants v JOIN model_packages p ON p.id=v.package_id WHERE v.id=?",
                    (plan.model_variant_id,),
                ).fetchone()
            finally:
                connection.close()
            if row is None:
                continue
            requirements = json.loads(str(row[3] or "{}"))
            providers = tuple(str(x).casefold() for x in requirements.get("providers", ()))
            device = "cpu"
            if any("cuda" in x for x in providers):
                try:
                    import torch

                    if torch.cuda.is_available():
                        device = "cuda"
                    else:
                        # Skip a CUDA-only active variant on CPU-only systems; a
                        # companion cpu-fp32 variant is installed by Quick Setup.
                        continue
                except ImportError:
                    continue
            artifact = Path(str(row[0])) / str(row[1])
            handle = provider.load(artifact, device=device, precision=str(row[2]))
            try:
                result = TaxonomyTextEmbeddingService(
                    labels=SqliteTaxonomyLabelSource(self._factory),
                    store=SqliteTaxonomyEmbeddingStore(self._factory),
                    embed_text=lambda texts, h=handle: provider.embed_text(h, texts),
                    public_id_factory=lambda _label: self._id_factory(),
                ).rebuild(
                    model_variant_id=plan.model_variant_id,
                    preprocessing_identity=plan.preprocessing_identity,
                    prompt_set_public_id=plan.prompt_set_public_id,
                    now_us=self._now_us(),
                )
                total_labels += result.labels_seen
                total_written += result.embeddings_written
            finally:
                provider.unload(handle)
        return total_labels, total_written
