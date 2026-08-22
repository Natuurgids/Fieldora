"""Translate stable engine results into Aperture-owned canonical records."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from natureai_next.application.enrichment import CanonicalEnrichment, CanonicalEnrichmentService
from natureai_next.domain.enrichment import EnrichmentStatus, SubjectRef
from natureai_next.synthesis_core.contracts import CapabilityResult


@dataclass(frozen=True, slots=True)
class TranslationOutcome:
    enrichment_ids: tuple[str, ...]


class CapabilityTranslationService:
    def __init__(
        self,
        database_path: Path,
        *,
        id_factory: Callable[[], str],
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._store = CanonicalEnrichmentService(database_path)
        self._id_factory = id_factory
        self._clock_us = clock_us or (lambda: time.time_ns() // 1000)

    def translate(self, subject: SubjectRef, result: CapabilityResult) -> TranslationOutcome:
        created: list[str] = []
        now = self._clock_us()
        snapshot = {
            "producer_name": result.producer_name,
            "producer_version": result.producer_version,
            "source_name": result.source_name,
            "source_version": result.source_version,
            "checksum": result.source_checksum,
            "attribution": result.attribution,
            "licence": result.licence,
            "created_at_us": now,
        }
        for candidate in result.candidates:
            enrichment_id = self._id_factory()
            payload = {
                "shape": candidate.shape.value,
                "value": dict(candidate.value),
                "target": dict(candidate.target),
                "external_id": candidate.external_id,
                "source_snapshot": snapshot,
            }
            self._store.store(
                CanonicalEnrichment(
                    enrichment_id=enrichment_id,
                    subject_type=subject.subject_type.value,
                    subject_public_id=subject.public_id,
                    enrichment_type=candidate.shape.value,
                    producer_id=result.capability_id,
                    producer_version=result.producer_version,
                    producer_run_id=result.run_id,
                    status=EnrichmentStatus.PENDING_REVIEW.value,
                    confidence=candidate.confidence,
                    summary=_summary(candidate.value),
                    payload=payload,
                    evidence={"diagnostics": dict(result.diagnostics)},
                    source_id=result.capability_id,
                    source_snapshot=snapshot,
                    created_at_us=now,
                    updated_at_us=now,
                )
            )
            created.append(enrichment_id)
        return TranslationOutcome(tuple(created))


def _summary(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("label", "scientific_name", "text", "name", "value"):
        item = value.get(key)
        if item is not None:
            return str(item)
    return None
