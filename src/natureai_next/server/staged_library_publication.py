"""Managed staged-ingestion publication into the governed organization Library.

The quarantine service owns validation and durable staging. This adapter supplies the
missing downstream publication boundary for the managed Platform composition: bytes
are registered as organization-owned Library evidence, optional Project context is a
separate association, and the staged row is marked published only after both succeed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from natureai_next.server.access_contracts import (
    AccessTarget,
    AccessTargetKind,
    ContractDraft,
)
from natureai_next.server.media import GovernedMediaStore
from natureai_next.server.media_links import new_association
from natureai_next.server.platform_extensions import (
    ProjectOptionalStagedIngestionStore,
)
from natureai_next.server.staged_ingestion import (
    StagedIngestionService,
    StagedSubmission,
)


_ACTIVE_MEDIA_STORE: GovernedMediaStore | None = None


class PublishingGovernedMediaStore(GovernedMediaStore):
    """Capture the managed media-store instance for the worker composition."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        global _ACTIVE_MEDIA_STORE
        _ACTIVE_MEDIA_STORE = self


class PublishingProjectOptionalStagedIngestionStore(ProjectOptionalStagedIngestionStore):
    """Snapshot a fail-closed access scope when browser intake begins."""

    def create_submission(
        self,
        *,
        subject_id: str,
        organization_id: str,
        project_id: str = "",
        contract_id: str = "",
        purpose: str,
        publication_policy: str,
        expected_files: int,
    ) -> StagedSubmission:
        submission = super().create_submission(
            subject_id=subject_id,
            organization_id=organization_id,
            project_id=project_id,
            contract_id=contract_id,
            purpose=purpose,
            publication_policy=publication_policy,
            expected_files=expected_files,
        )
        project = project_id.strip()
        target = (
            AccessTarget(AccessTargetKind.PROJECT, project_id=project)
            if project
            else AccessTarget(
                AccessTargetKind.ORGANIZATION,
                organization_id=organization_id.strip(),
            )
        )
        self.record_access_context(
            submission.submission_id,
            requested_by=subject_id,
            draft=ContractDraft(
                (target,),
                contract_id.strip(),
                False,
                0,
                source_project_id=project,
            ),
        )
        return submission


class PublishingStagedIngestionService(StagedIngestionService):
    """Publish processed staged files into Library evidence idempotently."""

    def process_batch(self, staged_file_ids: tuple[str, ...]) -> dict[str, object]:
        media = _ACTIVE_MEDIA_STORE
        if media is None:
            raise RuntimeError("managed media store is unavailable for staged publication")

        published = 0
        for staged_file_id in staged_file_ids:
            item = self.store.file(staged_file_id)
            if item is None:
                raise ValueError("staged file is unavailable for publication")
            if item.state == "validated":
                self.store.mark_processing((staged_file_id,))
                item = self.store.file(staged_file_id)
                assert item is not None
            if item.state == "processing":
                self.store.mark_processed((staged_file_id,))
                item = self.store.file(staged_file_id)
                assert item is not None
            if item.state == "published":
                published += 1
                continue
            if item.state != "processed":
                raise ValueError("staged file is unavailable for publication")

            submission = self.store.submission(item.submission_id)
            if submission is None:
                raise ValueError("staged submission is unavailable for publication")

            # The evidence record is Library-owned. A Project is context only and is
            # represented below by an association; it never changes evidence identity.
            record = media.register(
                Path(item.quarantine_path),
                submission.organization_id,
                "",
            )
            if submission.project_id:
                media.associations.link(
                    new_association(
                        media_id=record.media_id,
                        organization_id=submission.organization_id,
                        association_type="project",
                        target_id=submission.project_id,
                        purpose=submission.purpose,
                        linked_by=submission.subject_id,
                    )
                )
            self.store.mark_published(staged_file_id, record.media_id)
            published += 1

        return {"processed": len(staged_file_ids), "published": published}
