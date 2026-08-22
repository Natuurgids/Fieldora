"""Taxonomy administration, browsing, observations, and AI refresh orchestration."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from natureai_next.application.jobs import SubmitJob
from natureai_next.domain.jobs import ResourceClass
from natureai_next.domain.taxonomy import ObservationDraft, RegionOfInterestDraft
from natureai_next.ports.ai_review import (
    TaxonomyEmbeddingRefreshPlanSource,
    TaxonomyEmbeddingStore,
)
from natureai_next.ports.taxonomy import (
    ObservationPort,
    TaxonomyCatalogPort,
    TaxonomyPackageVerifier,
    UserTaxonPort,
)


class TaxonomyActivationHook(Protocol):
    def __call__(self, source_public_id: str, *, now_us: int) -> object: ...


class TaxonomyEmbeddingRefreshCoordinator:
    """Invalidates stale taxonomy vectors and queues deterministic rebuild jobs."""

    def __init__(
        self,
        *,
        plans: TaxonomyEmbeddingRefreshPlanSource,
        embeddings: TaxonomyEmbeddingStore,
        submit_job: Callable[[SubmitJob], object],
        language_tags: Sequence[str] = ("en", "nl", "bg"),
        region_codes: Sequence[str] = ("NL", "BG"),
        batch_size: int = 128,
    ) -> None:
        if not 1 <= batch_size <= 2048:
            raise ValueError("batch_size must be between 1 and 2048")
        self._plans = plans
        self._embeddings = embeddings
        self._submit_job = submit_job
        self._language_tags = tuple(
            dict.fromkeys(tag.strip() for tag in language_tags if tag.strip())
        )
        self._region_codes = tuple(
            dict.fromkeys(code.strip().upper() for code in region_codes if code.strip())
        )
        self._batch_size = batch_size

    def refresh(self, taxonomy_source_public_id: str, *, now_us: int) -> tuple[str, ...]:
        source_id = taxonomy_source_public_id.strip()
        if not source_id:
            raise ValueError("taxonomy_source_public_id is required")
        submitted: list[str] = []
        for plan in self._plans.active_plans():
            self._embeddings.invalidate(
                model_variant_id=plan.model_variant_id,
                preprocessing_identity=plan.preprocessing_identity,
                prompt_set_public_id=plan.prompt_set_public_id,
            )
            identity_material = "|".join(
                (
                    source_id,
                    str(plan.model_variant_id),
                    plan.preprocessing_identity,
                    plan.prompt_set_public_id or "",
                    ",".join(self._language_tags),
                    ",".join(self._region_codes),
                )
            )
            idempotency_key = (
                "taxonomy-text-refresh:"
                + hashlib.sha256(identity_material.encode("utf-8")).hexdigest()
            )
            result = self._submit_job(
                SubmitJob(
                    job_type="ai.embed_taxonomy_text.v1",
                    resource_class=ResourceClass.GPU,
                    priority=25,
                    idempotency_key=idempotency_key,
                    payload={
                        "schema_version": 1,
                        "taxonomy_source_public_id": source_id,
                        "model_variant_id": plan.model_variant_id,
                        "preprocessing_identity": plan.preprocessing_identity,
                        "prompt_set_public_id": plan.prompt_set_public_id,
                        "language_tags": list(self._language_tags),
                        "region_codes": list(self._region_codes),
                        "include_synonyms": True,
                        "batch_size": self._batch_size,
                        "now_us": now_us,
                    },
                )
            )
            public_id = getattr(result, "public_id", None)
            if public_id is not None:
                submitted.append(str(public_id))
        return tuple(submitted)


class TaxonomyAdministrationService:
    def __init__(
        self,
        verifier: TaxonomyPackageVerifier,
        catalog: TaxonomyCatalogPort,
        *,
        on_activated: TaxonomyActivationHook | None = None,
    ) -> None:
        self._verifier = verifier
        self._catalog = catalog
        self._on_activated = on_activated

    def install(self, path: Path, *, now_us: int) -> str:
        source_public_id = self._catalog.install(self._verifier.verify(path), now_us=now_us)
        if self._on_activated is not None:
            self._on_activated(source_public_id, now_us=now_us)
        return source_public_id

    def active_sources(self):
        return self._catalog.active_sources()

    def verify_closure(self, source_public_id: str) -> tuple[int, int]:
        return self._catalog.verify_closure(source_public_id)

    def rebuild_closure(self, source_public_id: str) -> None:
        self._catalog.rebuild_closure(source_public_id)


class TaxonomyBrowserService:
    def __init__(self, catalog: TaxonomyCatalogPort) -> None:
        self._catalog = catalog

    def search(self, text: str, **kwargs):
        return self._catalog.search(text, **kwargs)

    def children(self, parent_public_id: str | None, **kwargs):
        return self._catalog.children(parent_public_id, **kwargs)

    def detail(self, public_id: str, **kwargs):
        return self._catalog.detail(public_id, **kwargs)


class ObservationService:
    def __init__(self, observations: ObservationPort) -> None:
        self._observations = observations

    def create(self, **kwargs):
        draft: ObservationDraft = kwargs["draft"]
        draft.validate()
        return self._observations.create(**kwargs)

    def update(self, **kwargs):
        draft: ObservationDraft = kwargs["draft"]
        draft.validate()
        return self._observations.update(**kwargs)

    def list_for_asset(self, asset_public_id: str):
        return self._observations.list_for_asset(asset_public_id)

    def create_roi(self, **kwargs):
        draft: RegionOfInterestDraft = kwargs["draft"]
        draft.validate()
        return self._observations.create_roi(**kwargs)


class UserTaxonService:
    def __init__(self, store: UserTaxonPort) -> None:
        self._store = store

    def create(self, **kwargs) -> None:
        if not kwargs["display_name"].strip():
            raise ValueError("display name is required")
        self._store.create(**kwargs)

    def map_to_taxon(self, **kwargs) -> None:
        self._store.map_to_taxon(**kwargs)
