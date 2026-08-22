"""Contribution preview, terms acknowledgment, and conflict resolution."""

from __future__ import annotations

from dataclasses import dataclass

from natureai_next.domain.synchronization import ContributionAcknowledgment
from natureai_next.ports.synchronization import DesktopSynchronizationRepository


@dataclass(frozen=True, slots=True)
class ContributionPreview:
    enrollment_id: str
    change_count: int
    creates_or_updates: int
    deletions: int
    aggregate_types: tuple[str, ...]


class ContributionReviewService:
    def __init__(self, repository: DesktopSynchronizationRepository) -> None:
        self._repository = repository

    def preview(self, enrollment_id: str) -> ContributionPreview:
        changes = self._repository.pending_outbox(enrollment_id)
        return ContributionPreview(
            enrollment_id, len(changes),
            sum(not change.tombstone for change in changes),
            sum(change.tombstone for change in changes),
            tuple(sorted({change.aggregate_type for change in changes})),
        )

    def acknowledge(self, acknowledgment: ContributionAcknowledgment) -> None:
        if len(acknowledgment.terms_sha256) != 64:
            raise ValueError("terms SHA-256 is required")
        self._repository.acknowledge_contribution(acknowledgment)

    def resolve(
        self, conflict_id: str, *, resolution: str, payload: dict, resolved_at_utc: str
    ) -> None:
        self._repository.resolve_conflict(
            conflict_id, resolution=resolution, payload=payload,
            resolved_at_utc=resolved_at_utc,
        )
