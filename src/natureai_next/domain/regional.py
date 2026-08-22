"""Regional knowledge profile domain values."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegionalCountry:
    country_code: str
    continent_code: str
    country_name: str
    priority: int
    verified_by: str | None = None


@dataclass(frozen=True, slots=True)
class RegionalProfile:
    primary_continent_code: str | None
    countries: tuple[RegionalCountry, ...]
    include_global_fallback: bool = True
    preferred_languages: tuple[str, ...] = ("en", "scientific")

    @property
    def primary_region_code(self) -> str | None:
        return self.countries[0].country_code if self.countries else self.primary_continent_code


@dataclass(frozen=True, slots=True)
class RegionalEvidence:
    level: str
    label: str
    matched_region_code: str | None
    occurrence_status: str | None
    source: str | None
