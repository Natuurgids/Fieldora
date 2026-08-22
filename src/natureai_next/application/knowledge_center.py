"""Knowledge Center projections over reference taxonomy and library observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from natureai_next.domain.observation_intelligence import SpeciesObservationHistory
from natureai_next.domain.taxonomy import TaxonKnowledgeProfile


class TaxonKnowledgeSource(Protocol):
    def search(self, text: str, *, limit: int = 50) -> None: ...
    def profile(self, public_id: str) -> TaxonKnowledgeProfile: ...


class ObservationHistorySource(Protocol):
    def history_for_taxon(self, taxon_public_id: str) -> SpeciesObservationHistory: ...


class TaxonLinkSource(Protocol):
    def resolve_reference_taxon(
        self, *, library_public_id: str, local_taxon_public_id: str
    ) -> str | None: ...


@dataclass(frozen=True, slots=True)
class KnowledgeCenterTaxonCard:
    public_id: str
    scientific_name: str
    preferred_name: str | None
    rank: str
    status: str
    observation_count: int
    evidence_photo_count: int
    first_observed_at_us: int | None
    last_observed_at_us: int | None
    country_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeCenterTaxonPage:
    reference: TaxonKnowledgeProfile
    observation_history: SpeciesObservationHistory | None

    @property
    def locally_observed(self) -> bool:
        return bool(self.observation_history and self.observation_history.summary.observation_count)


class KnowledgeCenterService:
    """Combines reference knowledge with local evidence without cross-database joins."""

    def __init__(
        self,
        taxonomy: TaxonKnowledgeSource,
        observations: ObservationHistorySource | None = None,
        *,
        library_public_id: str | None = None,
        links: TaxonLinkSource | None = None,
    ) -> None:
        self._taxonomy = taxonomy
        self._observations = observations
        self._library_public_id = library_public_id
        self._links = links

    def search(self, text: str, *, limit: int = 50) -> tuple[KnowledgeCenterTaxonCard, ...]:
        target = text.strip()
        if not target:
            return ()
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        cards: list[KnowledgeCenterTaxonCard] = []
        for taxon in self._taxonomy.search(target, limit=limit):
            profile = self._taxonomy.profile(taxon.public_id)
            history = self._history_or_none(taxon.public_id)
            summary = None if history is None else history.summary
            cards.append(
                KnowledgeCenterTaxonCard(
                    public_id=taxon.public_id,
                    scientific_name=taxon.scientific_name,
                    preferred_name=profile.preferred_names[0] if profile.preferred_names else None,
                    rank=taxon.rank,
                    status=taxon.status,
                    observation_count=0 if summary is None else summary.observation_count,
                    evidence_photo_count=0 if summary is None else summary.evidence_photo_count,
                    first_observed_at_us=None if summary is None else summary.first_observed_at_us,
                    last_observed_at_us=None if summary is None else summary.last_observed_at_us,
                    country_codes=() if summary is None else summary.country_codes,
                )
            )
        return tuple(cards)

    def taxon_page_for_local_taxon(self, local_taxon_public_id: str) -> KnowledgeCenterTaxonPage:
        identity = local_taxon_public_id.strip()
        if not identity:
            raise ValueError("local taxon identity is required")
        reference_id = identity
        if self._links is not None and self._library_public_id is not None:
            reference_id = (
                self._links.resolve_reference_taxon(
                    library_public_id=self._library_public_id, local_taxon_public_id=identity
                )
                or identity
            )
        return self.taxon_page(reference_id)

    def taxon_page(self, public_id: str) -> KnowledgeCenterTaxonPage:
        identity = public_id.strip()
        if not identity:
            raise ValueError("taxon identity is required")
        return KnowledgeCenterTaxonPage(
            reference=self._taxonomy.profile(identity),
            observation_history=self._history_or_none(identity),
        )

    def _history_or_none(self, public_id: str) -> SpeciesObservationHistory | None:
        if self._observations is None:
            return None
        try:
            return self._observations.history_for_taxon(public_id)
        except KeyError:
            # A reference taxon may not yet exist in the active library taxonomy.
            return None
