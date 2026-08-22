"""User-controlled local BioCLIP suggestion generation."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from natureai_next import __version__
from natureai_next.application.ai_review import CosineCandidateRanker, SuggestionService
from natureai_next.application.asset_analysis import AssetAnalysisService, TaxonCandidateInput
from natureai_next.application.capability_translation import CapabilityTranslationService
from natureai_next.domain.ai import AnalysisStatus, ConfidenceBand, SuggestionCandidate
from natureai_next.domain.enrichment import (
    CanonicalCandidate,
    CanonicalShape,
    SubjectRef,
    SubjectType,
)
from natureai_next.infrastructure.ai.diagnostic_logging import write_event, write_exception
from natureai_next.infrastructure.ai.tree_of_life_classifier import TreeOfLifeClassifierAdapter
from natureai_next.ports.ai import AIExecutionProvider, AIRuntimeRepository, ImagePreprocessor
from natureai_next.ports.ai_generation import SuggestionGenerationSource, TaxonomyCandidateSource
from natureai_next.synthesis_core.contracts import CapabilityRequest, CapabilityResult, InputKind


@dataclass(frozen=True, slots=True)
class SuggestionGenerationResult:
    requested: int
    completed_assets: int
    failed: tuple[tuple[str, str], ...]
    suggestions_created: int
    canonical_enrichment_created: int = 0


class LocalSuggestionGenerationService:
    """Runs local model inference and persists auditable ranked evidence."""

    def __init__(
        self,
        *,
        source: SuggestionGenerationSource,
        ai_repository: AIRuntimeRepository,
        taxonomy_embeddings: TaxonomyCandidateSource,
        suggestions: SuggestionService,
        id_factory: Callable[[], str],
        now_us: Callable[[], int],
        provider: AIExecutionProvider,
        preprocessor_factory: Callable[[int, str], ImagePreprocessor],
        analyses: AssetAnalysisService | None = None,
        canonical_translation: CapabilityTranslationService | None = None,
        inference_snapshot_root: Path | None = None,
    ) -> None:
        self._source = source
        self._ai_repository = ai_repository
        self._taxonomy_embeddings = taxonomy_embeddings
        self._suggestions = suggestions
        self._id_factory = id_factory
        self._now_us = now_us
        self._provider = provider
        self._preprocessor_factory = preprocessor_factory
        self._analyses = analyses
        self._canonical_translation = canonical_translation
        self._inference_snapshot_root = inference_snapshot_root
        self._ranker = CosineCandidateRanker()

    def generate_selected(
        self,
        asset_public_ids: Sequence[str],
        *,
        limit: int = 10,
        cancellation_check: Callable[[], None] = lambda: None,
        progress: Callable[[int, int, str], None] = lambda _current, _total, _message: None,
    ) -> SuggestionGenerationResult:
        public_ids = tuple(dict.fromkeys(str(value) for value in asset_public_ids if str(value)))
        if not public_ids:
            raise ValueError(
                "Select at least one Library photograph before generating suggestions."
            )
        if limit < 1 or limit > 50:
            raise ValueError("Suggestion limit must be between 1 and 50.")
        context = self._source.active_context()
        candidates = tuple(
            item
            for item in self._taxonomy_embeddings.candidates(
                model_variant_id=context.model_variant_id,
                preprocessing_identity=context.preprocessing_identity,
            )
            if not item[0].startswith("group:")
        )
        # When Aperture taxonomy embeddings are unavailable, restore the original
        # NatureAI path: pybioclip supplies its bundled TreeOfLife-10M labels and
        # matching text embeddings. GBIF remains optional enrichment.
        catalog_model_key = (
            context.execution_provider.split(":", 1)[1]
            if context.execution_provider.startswith("catalog-capability:")
            else None
        )
        use_catalog_capability = catalog_model_key is not None
        use_tree_of_life = not candidates and not use_catalog_capability
        assets = self._source.asset_paths(public_ids)
        missing = tuple(value for value in public_ids if value not in {item[0] for item in assets})
        failures: list[tuple[str, str]] = [
            (value, "Asset has no readable primary file.") for value in missing
        ]
        run_id = self._ai_repository.begin_inference_run(
            public_id=self._id_factory(),
            model_variant_id=context.model_variant_id,
            execution_provider=f"{context.execution_provider}:{context.device}",
            precision=context.precision,
            application_version=__version__,
            requested_item_count=len(public_ids),
            parameters_json=json.dumps(
                {"scope": "selected", "limit": limit, "device": context.device},
                sort_keys=True,
            ),
        )
        completed = 0
        created = 0
        canonical_created = 0
        write_event(
            "inference-run-started",
            run_id=run_id,
            requested=len(public_ids),
            model=context.model_identity,
            model_version=context.model_version,
            provider=context.execution_provider,
            device=context.device,
            prompt_set=context.prompt_set_public_id,
        )
        model: object | None = None
        catalog_capability = None
        tree_of_life: TreeOfLifeClassifierAdapter | None = None
        try:
            if use_catalog_capability:
                manager = getattr(self._provider, "manager", None)
                if manager is None:
                    raise RuntimeError("The active catalog model manager is unavailable.")
                catalog_capability = manager.instantiate(catalog_model_key)
                preprocessor = None
            elif use_tree_of_life:
                tree_of_life = TreeOfLifeClassifierAdapter(device=context.device)
                tree_of_life.load()
                preprocessor = None
            else:
                model = self._provider.load(
                    context.artifact_path, device=context.device, precision=context.precision
                )
                preprocessor = self._preprocessor_factory(
                    context.input_size, context.preprocessing_identity
                )
            total = len(assets)
            progress(0, total, "Loading BioCLIP model")
            for index, (asset_public_id, path) in enumerate(assets, start=1):
                cancellation_check()
                analysis_public_id: str | None = None
                try:
                    if not path.is_file():
                        raise FileNotFoundError(path)
                    configuration = {
                        "limit": limit,
                        "variant_identity": context.variant_identity,
                        "preprocessing_identity": context.preprocessing_identity,
                        "execution_provider": context.execution_provider,
                        "device": context.device,
                        "precision": context.precision,
                        "prompt_set_public_id": context.prompt_set_public_id,
                    }
                    if self._analyses is not None:
                        analysis_public_id = self._analyses.start(
                            asset_public_id=asset_public_id,
                            engine_id="ai.bioclip",
                            engine_family="bioclip",
                            analysis_kind="taxon_classification",
                            model_name=context.model_identity,
                            model_version=context.model_version,
                            configuration=configuration,
                        )
                    snapshot_relative_path: str | None = None
                    snapshot_image = None
                    # Visual provenance is valuable, but it must never make an otherwise
                    # valid inference fail.  The pybioclip Tree-of-Life path performs its
                    # own preprocessing, so snapshot creation is deliberately best-effort.
                    try:
                        snapshot_preprocessor = self._preprocessor_factory(
                            context.input_size, context.preprocessing_identity
                        )
                        snapshot_image = snapshot_preprocessor.prepare(path)
                        if self._inference_snapshot_root is not None:
                            snapshot_path = (
                                self._inference_snapshot_root
                                / run_id
                                / f"{asset_public_id}.jpg"
                            )
                            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                            temporary = snapshot_path.with_suffix(".tmp.jpg")
                            rgb_snapshot = snapshot_image.convert("RGB")
                            rgb_snapshot.save(
                                temporary, format="JPEG", quality=92, optimize=True
                            )
                            temporary.replace(snapshot_path)
                            snapshot_relative_path = str(
                                snapshot_path.relative_to(
                                    self._inference_snapshot_root.parent.parent
                                )
                            )
                    except Exception as snapshot_exc:
                        write_exception(
                            "inference-input-snapshot-failed",
                            snapshot_exc,
                            run_id=run_id,
                            asset_id=asset_public_id,
                            image_path=str(path),
                        )
                    if use_catalog_capability:
                        assert catalog_capability is not None
                        capability_result = catalog_capability.execute(
                            CapabilityRequest(
                                capability_id=catalog_capability.descriptor.capability_id,
                                subject_public_id=asset_public_id,
                                input_kind=InputKind.PHOTO,
                                input_path=path,
                                parameters={"limit": limit},
                            )
                        )
                        ranked_items = []
                        for rank, candidate in enumerate(capability_result.candidates[:limit], start=1):
                            payload = dict(candidate.payload)
                            label = str(payload.get("label") or payload.get("common_name") or payload.get("scientific_name") or "Unknown")
                            score = float(candidate.confidence or 0.0)
                            band = (ConfidenceBand.HIGH if score >= 0.30 else ConfidenceBand.MEDIUM if score >= 0.20 else ConfidenceBand.LOW if score >= 0.10 else ConfidenceBand.UNKNOWN)
                            ranked_items.append(SuggestionCandidate(None, label, score, rank, score, band, str(payload.get("rank") or "species")))
                        ranked = tuple(ranked_items)
                    elif use_tree_of_life:
                        assert tree_of_life is not None
                        ranked = tree_of_life.predict(path, limit=limit)
                    else:
                        assert model is not None
                        if snapshot_image is None:
                            snapshot_image = preprocessor.prepare(path)
                        vectors = self._provider.embed_images(model, (snapshot_image,))
                        if len(vectors) != 1:
                            raise RuntimeError(
                                "The model returned an unexpected image-vector count."
                            )
                        ranked = self._ranker.rank(
                            vectors[0], candidates, region_code=None, limit=limit
                        )
                    if not ranked:
                        raise RuntimeError("No compatible taxonomy candidates were produced.")
                    write_event(
                        "classifier-result",
                        level="detailed",
                        run_id=run_id,
                        asset_id=asset_public_id,
                        image_path=str(path),
                        candidate_count=len(ranked),
                        candidates=[
                            {
                                "label": item.label,
                                "raw_score": item.raw_score,
                                "rank": item.rank,
                                "external_taxon_id": item.taxon_public_id,
                            }
                            for item in ranked
                        ],
                    )
                    created_ids = self._suggestions.create(
                        asset_public_id=asset_public_id,
                        inference_run_id=run_id,
                        suggestions=ranked,
                        prompt_set_id=context.prompt_set_public_id,
                        analysis_public_id=analysis_public_id,
                        provenance={
                            "application_version": __version__,
                            "model_identity": context.model_identity,
                            "model_version": context.model_version,
                            "variant_identity": context.variant_identity,
                            "preprocessing_identity": context.preprocessing_identity,
                            "execution_provider": context.execution_provider,
                            "device": context.device,
                            "precision": context.precision,
                            "analysis_public_id": analysis_public_id,
                            "inference_image_relative_path": snapshot_relative_path,
                            "inference_image_width": context.input_size,
                            "inference_image_height": context.input_size,
                            "classification_source": (
                                f"catalog-capability:{catalog_model_key}"
                                if use_catalog_capability
                                else "pybioclip-tree-of-life"
                                if use_tree_of_life
                                else "aperture-taxonomy-embeddings"
                            ),
                            "external_candidates": (
                                list(tree_of_life.last_prediction_rows)
                                if use_tree_of_life and tree_of_life is not None
                                else []
                            ),
                        },
                        geographic_context={},
                        now_us=self._now_us(),
                        id_factory=self._id_factory,
                    )
                    if self._analyses is not None and analysis_public_id is not None:
                        self._analyses.complete(
                            analysis_public_id,
                            summary={
                                "candidate_count": len(ranked),
                                "suggestion_count": len(created_ids),
                                "top_label": ranked[0].label,
                                "top_score": ranked[0].calibrated_score,
                            },
                            candidates=tuple(
                                TaxonCandidateInput(
                                    label=item.label,
                                    rank=item.rank,
                                    raw_score=item.raw_score,
                                    calibrated_score=item.calibrated_score,
                                    confidence_band=item.confidence_band,
                                    local_taxon_public_id=item.taxon_public_id,
                                    taxonomic_level=item.taxonomic_level,
                                    provenance={"suggestion_public_id": suggestion_id},
                                )
                                for item, suggestion_id in zip(ranked, created_ids, strict=True)
                            ),
                        )
                    created += len(created_ids)
                    if self._canonical_translation is not None:
                        canonical_result = CapabilityResult(
                            capability_id="aperture.bioclip",
                            producer_name=context.model_identity,
                            producer_version=context.model_version or __version__,
                            run_id=run_id,
                            source_name=(
                                capability_result.source_name
                                if use_catalog_capability
                                else "BioCLIP TreeOfLife-10M"
                                if use_tree_of_life
                                else "Aperture taxonomy embeddings"
                            ),
                            source_version=context.prompt_set_public_id,
                            attribution="BioCLIP and TreeOfLife contributors",
                            licence="See installed BioCLIP resource licence",
                            diagnostics={"legacy_suggestion_ids": list(created_ids)},
                            candidates=tuple(
                                CanonicalCandidate(
                                    CanonicalShape.TAXONOMY_CANDIDATE,
                                    {
                                        "label": item.label,
                                        "scientific_name": item.label.split(" (", 1)[0],
                                        "rank": item.taxonomic_level or "species",
                                    },
                                    confidence=item.calibrated_score,
                                    external_id=item.taxon_public_id,
                                )
                                for item in ranked
                            ),
                        )
                        outcome = self._canonical_translation.translate(
                            SubjectRef(SubjectType.PHOTO, asset_public_id), canonical_result
                        )
                        canonical_created += len(outcome.enrichment_ids)
                    completed += 1
                except Exception as exc:
                    write_exception(
                        "inference-item-failed",
                        exc,
                        run_id=run_id,
                        asset_id=asset_public_id,
                        image_path=str(path),
                        stage="classify-or-persist",
                        model=context.model_identity,
                        model_version=context.model_version,
                        provider=context.execution_provider,
                        device=context.device,
                        prompt_set=context.prompt_set_public_id,
                        detailed_fields={
                            "classifier_rows": list(tree_of_life.last_prediction_rows)
                            if use_tree_of_life and tree_of_life is not None
                            else []
                        },
                    )
                    if self._analyses is not None and analysis_public_id is not None:
                        with contextlib.suppress(Exception):
                            self._analyses.complete(
                                analysis_public_id,
                                status=AnalysisStatus.FAILED,
                                summary={"error": str(exc)},
                            )
                    failures.append((asset_public_id, str(exc)))
                progress(index, total, f"Processed {index} of {total}")
            self._ai_repository.finish_inference_run(
                run_id,
                completed=completed,
                failed=len(failures),
                retries=0,
                final_batch_size=1,
                error_text=None,
            )
            write_event(
                "inference-run-finished",
                run_id=run_id,
                requested=len(public_ids),
                completed=completed,
                failed=len(failures),
                suggestions_created=created,
            )
            return SuggestionGenerationResult(
                len(public_ids), completed, tuple(failures), created, canonical_created
            )
        except Exception as exc:
            write_exception(
                "inference-run-failed",
                exc,
                run_id=run_id,
                completed=completed,
                requested=len(public_ids),
                stage="run",
            )
            self._ai_repository.finish_inference_run(
                run_id,
                completed=completed,
                failed=max(1, len(public_ids) - completed),
                retries=0,
                final_batch_size=1,
                error_text=str(exc),
            )
            raise
        finally:
            if model is not None:
                self._provider.unload(model)
