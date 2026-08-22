"""Regional profile application service."""

from __future__ import annotations

from natureai_next.domain.regional import RegionalProfile


class RegionalProfileService:
    def __init__(self, store: object, *, now_us: object) -> None:
        self._store = store
        self._now_us = now_us

    def load(self) -> RegionalProfile:
        return self._store.load()

    def save(self, profile: RegionalProfile) -> RegionalProfile:
        if not profile.primary_continent_code and not profile.countries:
            raise ValueError("Select at least one continent or country.")
        if not profile.preferred_languages:
            raise ValueError("Select at least one display language.")
        return self._store.save(profile, now_us=int(self._now_us()))

    def primary_region_code(self) -> str | None:
        return self.load().primary_region_code

    def evidence_for_taxon(self, taxon_public_id: str | None):
        return self._store.evidence_for_taxon(taxon_public_id)
