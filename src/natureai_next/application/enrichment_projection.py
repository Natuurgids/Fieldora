"""Subject-centric projection of producer-neutral enrichment records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from natureai_next.application.enrichment import CanonicalEnrichmentService
from natureai_next.application.observation_links import ObservationLinkService
from natureai_next.domain.enrichment import EnrichmentStatus, SubjectRef, SubjectType


@dataclass(frozen=True, slots=True)
class ProjectedEnrichment:
    enrichment_id: str
    shape: str
    status: str
    summary: str | None
    value: dict[str, Any]
    target: dict[str, Any]
    confidence: float | None
    provenance: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SubjectEnrichmentView:
    subject: SubjectRef
    items: tuple[ProjectedEnrichment, ...]

    @property
    def pending(self) -> tuple[ProjectedEnrichment, ...]:
        return tuple(item for item in self.items if item.status == EnrichmentStatus.PENDING_REVIEW)

    @property
    def accepted(self) -> tuple[ProjectedEnrichment, ...]:
        return tuple(item for item in self.items if item.status == EnrichmentStatus.ACCEPTED)


class EnrichmentProjectionService:
    def __init__(self, database_path: Path) -> None:
        self._store = CanonicalEnrichmentService(database_path)
        self._links = ObservationLinkService(database_path)

    def for_subject(
        self,
        subject: SubjectRef,
        *,
        include_rejected: bool = False,
    ) -> SubjectEnrichmentView:
        records = self._store.list_for_subject(
            subject.subject_type.value,
            subject.public_id,
            include_rejected=include_rejected,
        )
        return SubjectEnrichmentView(
            subject,
            tuple(
                ProjectedEnrichment(
                    enrichment_id=item.enrichment_id,
                    shape=item.enrichment_type,
                    status=item.status,
                    summary=item.summary,
                    value=dict(item.payload.get("value", {})),
                    target=dict(item.payload.get("target", {})),
                    confidence=item.confidence,
                    provenance=dict(item.payload.get("source_snapshot", {})),
                )
                for item in records
            ),
        )

    def for_observation(
        self,
        observation_public_id: str,
        linked_subjects: tuple[SubjectRef, ...] | None = None,
    ) -> SubjectEnrichmentView:
        observation = SubjectRef(
            subject_type=SubjectType.OBSERVATION, public_id=observation_public_id
        )
        collected: list[ProjectedEnrichment] = []
        subjects = (
            linked_subjects
            if linked_subjects is not None
            else self._links.linked_subjects(observation_public_id)
        )
        for subject in subjects:
            collected.extend(self.for_subject(subject).accepted)
        collected.extend(self.for_subject(observation).accepted)
        return SubjectEnrichmentView(observation, tuple(collected))
