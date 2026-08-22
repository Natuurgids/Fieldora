"""Subject-centric execution façade for structured source/importer plugins."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from natureai_next.application.enrichment_projection import (
    EnrichmentProjectionService,
    SubjectEnrichmentView,
)
from natureai_next.application.source_translation import SourceTranslationService
from natureai_next.domain.enrichment import SubjectRef
from natureai_next.synthesis_core.sources import InProcessSourceRouter, SourceImportRequest


@dataclass(frozen=True, slots=True)
class SourceWorkspaceOutcome:
    created_enrichment_ids: tuple[str, ...]
    projection: SubjectEnrichmentView


class SourceWorkspaceService:
    def __init__(
        self, database_path: Path, router: InProcessSourceRouter, *, id_factory, clock_us=None
    ) -> None:
        self._router = router
        self._translation = SourceTranslationService(
            database_path, id_factory=id_factory, clock_us=clock_us
        )
        self._projection = EnrichmentProjectionService(database_path)

    def discover_sources(self):
        return self._router.discover()

    def import_file(
        self,
        subject: SubjectRef,
        *,
        source_id: str,
        input_path: Path,
        parameters: Mapping[str, Any] | None = None,
    ) -> SourceWorkspaceOutcome:
        result = self._router.execute(
            SourceImportRequest(
                source_id=source_id,
                subject_public_id=subject.public_id,
                input_path=input_path,
                parameters=parameters or {},
            )
        )
        translated = self._translation.translate(subject, result)
        return SourceWorkspaceOutcome(
            translated.enrichment_ids,
            self._projection.for_subject(subject, include_rejected=True),
        )
