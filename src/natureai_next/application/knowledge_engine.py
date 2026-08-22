"""Cross-domain knowledge synthesis without authoritative data ownership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from natureai_next.domain.ai import AssetAnalysisRecord
from natureai_next.domain.observation_intelligence import (
    PersonalObservationContext,
    SpeciesObservationHistory,
    SpeciesObservationSummary,
)
from natureai_next.domain.spatial_intelligence import GeoBounds, SpatialObservation


class KnowledgeTaxonomySource(Protocol):
    def profile(self, public_id: str) -> None: ...


class KnowledgeObservationSource(Protocol):
    def list_species(self, *, limit: int = 500) -> tuple[SpeciesObservationSummary, ...]: ...
    def history_for_taxon(self, taxon_public_id: str) -> SpeciesObservationHistory: ...
    def context_for_taxon(
        self, taxon_public_id: str | None
    ) -> PersonalObservationContext | None: ...
    def related_taxa(
        self, taxon_public_id: str, *, limit: int = 8
    ) -> tuple[tuple[str, str, str | None], ...]: ...


class KnowledgeSpatialSource(Protocol):
    def observations_in_bounds(
        self, bounds: GeoBounds, *, limit: int = 5000
    ) -> tuple[SpatialObservation, ...]: ...


class KnowledgeAnalysisSource(Protocol):
    def list_for_asset(self, asset_public_id: str) -> tuple[AssetAnalysisRecord, ...]: ...
    def list_candidates_for_asset(self, asset_public_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class EvidenceScore:
    observation_count: int
    evidence_photo_count: int
    country_count: int
    verified_observation_ratio: float
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TaxonKnowledgeDossier:
    reference_profile: object | None
    observation_history: SpeciesObservationHistory | None
    evidence: EvidenceScore


@dataclass(frozen=True, slots=True)
class AssetEnrichmentDossier:
    asset_public_id: str
    analyses: tuple[AssetAnalysisRecord, ...]
    candidates: tuple[object, ...]
    engine_ids: tuple[str, ...]
    latest_completed_at_us: int | None


class KnowledgeEngine:
    """Sole application-level orchestrator for cross-domain knowledge queries."""

    def __init__(
        self,
        *,
        taxonomy: KnowledgeTaxonomySource | None = None,
        observations: KnowledgeObservationSource | None = None,
        spatial: KnowledgeSpatialSource | None = None,
        analyses: KnowledgeAnalysisSource | None = None,
    ) -> None:
        self._taxonomy = taxonomy
        self._observations = observations
        self._spatial = spatial
        self._analyses = analyses

    def taxon_dossier(
        self, taxon_public_id: str, *, observation_taxon_public_id: str | None = None
    ) -> TaxonKnowledgeDossier:
        identity = taxon_public_id.strip()
        if not identity:
            raise ValueError("taxon identity is required")
        profile = None
        history = None
        if self._taxonomy is not None:
            try:
                profile = self._taxonomy.profile(identity)
            except KeyError:
                profile = None
        if self._observations is not None:
            observation_identity = (observation_taxon_public_id or identity).strip()
            try:
                history = self._observations.history_for_taxon(observation_identity)
            except KeyError:
                history = None
        summary = None if history is None else history.summary
        observations = 0 if summary is None else summary.observation_count
        photos = 0 if summary is None else summary.evidence_photo_count
        countries = 0 if summary is None else len(summary.country_codes)
        ratio = 1.0 if observations else 0.0
        score = (
            min(1.0, observations / 10.0) * 0.55
            + min(1.0, photos / 20.0) * 0.30
            + min(1.0, countries / 5.0) * 0.15
        )
        reasons: list[str] = []
        if observations:
            reasons.append(f"{observations} confirmed observation(s)")
        if photos:
            reasons.append(f"{photos} evidence photo(s)")
        if countries:
            reasons.append(f"observed in {countries} countr{'y' if countries == 1 else 'ies'}")
        if not reasons:
            reasons.append("no confirmed local evidence")
        return TaxonKnowledgeDossier(
            reference_profile=profile,
            observation_history=history,
            evidence=EvidenceScore(
                observations, photos, countries, ratio, round(score, 4), tuple(reasons)
            ),
        )

    def observation_species(self, *, limit: int = 500) -> tuple[SpeciesObservationSummary, ...]:
        if self._observations is None:
            return ()
        if not 1 <= limit <= 5000:
            raise ValueError("limit must be between 1 and 5000")
        return self._observations.list_species(limit=limit)

    def observation_history(self, taxon_public_id: str) -> SpeciesObservationHistory:
        identity = taxon_public_id.strip()
        if not identity:
            raise ValueError("taxon identity is required")
        if self._observations is None:
            raise KeyError(identity)
        return self._observations.history_for_taxon(identity)

    def observation_context(self, taxon_public_id: str | None) -> PersonalObservationContext | None:
        if self._observations is None:
            return None
        return self._observations.context_for_taxon(taxon_public_id)

    def related_taxa(
        self, taxon_public_id: str, *, limit: int = 8
    ) -> tuple[tuple[str, str, str | None], ...]:
        identity = taxon_public_id.strip()
        if not identity:
            raise ValueError("taxon identity is required")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        if self._observations is None:
            return ()
        return self._observations.related_taxa(identity, limit=limit)

    def observations_in_area(
        self, bounds: GeoBounds, *, limit: int = 5000
    ) -> tuple[SpatialObservation, ...]:
        if self._spatial is None:
            return ()
        if not 1 <= limit <= 50_000:
            raise ValueError("limit must be between 1 and 50000")
        return self._spatial.observations_in_bounds(bounds, limit=limit)

    def asset_enrichment(self, asset_public_id: str) -> AssetEnrichmentDossier:
        identity = asset_public_id.strip()
        if not identity:
            raise ValueError("asset identity is required")
        if self._analyses is None:
            return AssetEnrichmentDossier(identity, (), (), (), None)
        analyses = self._analyses.list_for_asset(identity)
        candidates = tuple(self._analyses.list_candidates_for_asset(identity))
        engines = tuple(dict.fromkeys(item.engine_id for item in analyses))
        completed = [item.completed_at_us for item in analyses if item.completed_at_us is not None]
        return AssetEnrichmentDossier(
            identity, analyses, candidates, engines, max(completed) if completed else None
        )
