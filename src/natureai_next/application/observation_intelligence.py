"""Observation history, species summaries, and multi-photo evidence services."""

from __future__ import annotations

from typing import Protocol

from natureai_next.domain.observation_intelligence import (
    ObservationInspectorRecord,
    ObservationStatistics,
    PersonalObservationContext,
    SpeciesObservationHistory,
    SpeciesObservationSummary,
)


class ObservationIntelligencePort(Protocol):
    def context_for_taxon(self, taxon_public_id: str) -> PersonalObservationContext: ...
    def link_asset(
        self, observation_public_id: str, asset_public_id: str, *, now_us: int
    ) -> None: ...
    def set_context(
        self,
        observation_public_id: str,
        *,
        observed_at_us: int | None,
        latitude: float | None,
        longitude: float | None,
        altitude_m: float | None,
        accuracy_m: float | None,
        now_us: int,
        source: str = "user",
    ) -> None: ...
    def inspect(self, observation_public_id: str) -> ObservationInspectorRecord: ...
    def list_species(self, *, limit: int = 500) -> tuple[SpeciesObservationSummary, ...]: ...
    def history_for_taxon(self, taxon_public_id: str) -> SpeciesObservationHistory: ...
    def statistics(self, *, current_year: int) -> ObservationStatistics: ...
    def related_taxa(
        self, taxon_public_id: str, *, limit: int = 8
    ) -> tuple[tuple[str, str, str | None], ...]: ...


class ObservationIntelligenceService:
    def __init__(self, port: ObservationIntelligencePort) -> None:
        self._port = port

    def context_for_taxon(self, taxon_public_id: str | None) -> PersonalObservationContext | None:
        if not taxon_public_id:
            return None
        return self._port.context_for_taxon(taxon_public_id)

    def link_photo(self, observation_public_id: str, asset_public_id: str, *, now_us: int) -> None:
        if not observation_public_id.strip() or not asset_public_id.strip():
            raise ValueError("observation and asset identities are required")
        self._port.link_asset(observation_public_id, asset_public_id, now_us=now_us)

    def set_context(
        self,
        observation_public_id: str,
        *,
        observed_at_us: int | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        altitude_m: float | None = None,
        accuracy_m: float | None = None,
        now_us: int,
        source: str = "user",
    ) -> None:
        if not observation_public_id.strip():
            raise ValueError("observation identity is required")
        self._port.set_context(
            observation_public_id,
            observed_at_us=observed_at_us,
            latitude=latitude,
            longitude=longitude,
            altitude_m=altitude_m,
            accuracy_m=accuracy_m,
            now_us=now_us,
            source=source,
        )

    def inspect(self, observation_public_id: str) -> ObservationInspectorRecord:
        return self._port.inspect(observation_public_id)

    def list_species(self, *, limit: int = 500) -> tuple[SpeciesObservationSummary, ...]:
        if limit < 1 or limit > 5000:
            raise ValueError("limit must be between 1 and 5000")
        return self._port.list_species(limit=limit)

    def history_for_taxon(self, taxon_public_id: str) -> SpeciesObservationHistory:
        if not taxon_public_id.strip():
            raise ValueError("taxon identity is required")
        return self._port.history_for_taxon(taxon_public_id)

    def related_taxa(
        self, taxon_public_id: str, *, limit: int = 8
    ) -> tuple[tuple[str, str, str | None], ...]:
        if not taxon_public_id.strip():
            raise ValueError("taxon identity is required")
        if limit < 1 or limit > 50:
            raise ValueError("limit must be between 1 and 50")
        return self._port.related_taxa(taxon_public_id, limit=limit)

    def statistics(self, *, current_year: int) -> ObservationStatistics:
        if current_year < 1900 or current_year > 9999:
            raise ValueError("current_year is invalid")
        return self._port.statistics(current_year=current_year)
