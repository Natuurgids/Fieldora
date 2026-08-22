"""Headless presentation controller for canonical enrichment workspaces."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from natureai_next.application.enrichment_projection import SubjectEnrichmentView
from natureai_next.application.enrichment_workspace import EnrichmentWorkspaceService
from natureai_next.domain.enrichment import EnrichmentStatus, SubjectRef
from natureai_next.synthesis_core.contracts import InputKind
from natureai_next.ui.enrichment.renderers import (
    EnrichmentRendererRegistry,
    RenderedEnrichment,
    default_renderer_registry,
)


@dataclass(frozen=True, slots=True)
class EnrichmentWorkspacePresentation:
    subject: SubjectRef
    items: tuple[RenderedEnrichment, ...]
    generated_count: int
    pending_count: int
    accepted_count: int
    rejected_count: int


class EnrichmentWorkspaceController:
    """Converts application projections into reusable renderer-neutral UI models."""

    def __init__(
        self,
        workspace: EnrichmentWorkspaceService,
        *,
        registry: EnrichmentRendererRegistry | None = None,
        reviewer_provider: Callable[[], str] = lambda: "local-user",
    ) -> None:
        self._workspace = workspace
        self._registry = registry or default_renderer_registry()
        self._reviewer_provider = reviewer_provider

    def capabilities_for(self, input_kind: InputKind):
        return self._workspace.capabilities_for(input_kind)

    @property
    def capability_router(self):
        return self._workspace.capability_router

    def run_capability(
        self,
        subject: SubjectRef,
        *,
        capability_id: str,
        input_kind: InputKind,
        input_path=None,
        structured_input=None,
        parameters=None,
    ) -> EnrichmentWorkspacePresentation:
        outcome = self._workspace.run(
            subject,
            capability_id=capability_id,
            input_kind=input_kind,
            input_path=input_path,
            structured_input=structured_input,
            parameters=parameters,
        )
        return self._present(outcome.projection)

    def run_capability_async(
        self,
        subject: SubjectRef,
        *,
        capability_id: str,
        input_kind: InputKind,
        input_path=None,
        structured_input=None,
        parameters=None,
    ):
        return self._workspace.run_async(
            subject,
            capability_id=capability_id,
            input_kind=input_kind,
            input_path=input_path,
            structured_input=structured_input,
            parameters=parameters,
        )

    def run_capability_batch_async(self, items, **kwargs):
        return self._workspace.run_batch_async(items, **kwargs)

    def run_region_pipeline_async(self, subject: SubjectRef, **kwargs):
        return self._workspace.run_region_pipeline_async(subject, **kwargs)

    def load(
        self, subject: SubjectRef, *, include_rejected: bool = True
    ) -> EnrichmentWorkspacePresentation:
        return self._present(self._workspace.project(subject, include_rejected=include_rejected))

    def accept(self, subject: SubjectRef, enrichment_id: str) -> EnrichmentWorkspacePresentation:
        view = self._workspace.review(
            subject,
            enrichment_id,
            EnrichmentStatus.ACCEPTED,
            reviewer=self._reviewer_provider(),
        )
        return self._present(view)

    def reject(self, subject: SubjectRef, enrichment_id: str) -> EnrichmentWorkspacePresentation:
        view = self._workspace.review(
            subject,
            enrichment_id,
            EnrichmentStatus.REJECTED,
            reviewer=self._reviewer_provider(),
        )
        return self._present(view)

    def assign_review(
        self,
        subject: SubjectRef,
        enrichment_id: str,
        assigned_to: str | None,
        *,
        note: str = "",
    ) -> EnrichmentWorkspacePresentation:
        view = self._workspace.assign_review(
            subject,
            enrichment_id,
            assigned_to=assigned_to,
            assigned_by=self._reviewer_provider(),
            note=note,
        )
        return self._present(view)

    def _present(self, view: SubjectEnrichmentView) -> EnrichmentWorkspacePresentation:
        rendered = tuple(self._registry.render(item) for item in view.items)
        statuses = tuple(item.status for item in view.items)
        return EnrichmentWorkspacePresentation(
            subject=view.subject,
            items=rendered,
            generated_count=statuses.count(EnrichmentStatus.GENERATED.value),
            pending_count=statuses.count(EnrichmentStatus.PENDING_REVIEW.value),
            accepted_count=statuses.count(EnrichmentStatus.ACCEPTED.value),
            rejected_count=statuses.count(EnrichmentStatus.REJECTED.value),
        )
