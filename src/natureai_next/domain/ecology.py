"""Ecological context projections."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EcologicalContext:
    taxon_public_id: str
    scientific_name: str
    conservation_status: str | None
    seasonal_months: tuple[int, ...]
    migration_status: str | None
    habitats: tuple[str, ...]
    source_name: str
    source_version: str | None
    source_url: str | None

    def season_label(self, month: int | None) -> str:
        if not self.seasonal_months or month is None:
            return "Seasonality not available"
        return "Expected this month" if month in self.seasonal_months else "Outside recorded season"
