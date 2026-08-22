"""Presentation-safe retention orchestration for deliberate data slimming."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from natureai_next.application.retention import (
    EnrichmentRetentionPolicy,
    EnrichmentSlimmingReport,
    EnrichmentSlimmingService,
    RetentionProfileName,
)


@dataclass(frozen=True, slots=True)
class RetentionPreview:
    profile: RetentionProfileName
    policy: EnrichmentRetentionPolicy
    report: EnrichmentSlimmingReport
    destructive_accepted_delete: bool


class EnrichmentRetentionController:
    def __init__(self, database_path: Path) -> None:
        self._service = EnrichmentSlimmingService(database_path)

    def preview(
        self,
        profile: RetentionProfileName,
        *,
        delete_unselected_accepted: bool = False,
    ) -> RetentionPreview:
        policy = EnrichmentRetentionPolicy.named(profile)
        if delete_unselected_accepted:
            policy = EnrichmentRetentionPolicy(
                **{
                    name: getattr(policy, name)
                    for name in policy.__dataclass_fields__
                    if name != "delete_unselected_accepted"
                },
                delete_unselected_accepted=True,
            )
        return RetentionPreview(
            profile,
            policy,
            self._service.preview(policy),
            delete_unselected_accepted,
        )

    def apply(self, preview: RetentionPreview) -> EnrichmentSlimmingReport:
        return self._service.apply(preview.policy)
