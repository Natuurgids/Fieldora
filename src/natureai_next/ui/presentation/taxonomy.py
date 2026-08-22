"""GUI-independent taxonomy browser and observation editor models."""

from __future__ import annotations

from dataclasses import dataclass, replace

from natureai_next.application.taxonomy import ObservationService, TaxonomyBrowserService
from natureai_next.domain.taxonomy import (
    ConfirmationState,
    ObservationDraft,
    ObservationType,
    TaxonSummary,
)


@dataclass(frozen=True, slots=True)
class TaxonomyBrowserState:
    query: str = ""
    region_code: str | None = None
    language_tag: str | None = None
    results: tuple[TaxonSummary, ...] = ()
    selected_public_id: str | None = None
    error: str | None = None


class TaxonomyBrowserModel:
    def __init__(self, service: TaxonomyBrowserService) -> None:
        self._service = service
        self.state = TaxonomyBrowserState()

    def search(self, query: str) -> TaxonomyBrowserState:
        try:
            self.state = replace(
                self.state,
                query=query,
                results=self._service.search(
                    query, language_tag=self.state.language_tag, region_code=self.state.region_code
                ),
                error=None,
            )
        except Exception as exc:
            self.state = replace(self.state, error=str(exc))
        return self.state

    def set_preferences(
        self, *, language_tag: str | None, region_code: str | None
    ) -> TaxonomyBrowserState:
        self.state = replace(self.state, language_tag=language_tag, region_code=region_code)
        return self.state

    def select(self, public_id: str | None) -> TaxonomyBrowserState:
        self.state = replace(self.state, selected_public_id=public_id)
        return self.state


@dataclass(frozen=True, slots=True)
class ObservationEditorState:
    public_id: str | None = None
    revision: int | None = None
    draft: ObservationDraft = ObservationDraft(ObservationType.UNKNOWN)
    dirty: bool = False
    error: str | None = None


class ObservationEditorModel:
    def __init__(self, service: ObservationService) -> None:
        self._service = service
        self.state = ObservationEditorState()

    def edit(self, **changes: object) -> ObservationEditorState:
        self.state = replace(
            self.state, draft=replace(self.state.draft, **changes), dirty=True, error=None
        )
        return self.state

    def load(self, view) -> ObservationEditorState:
        draft = ObservationDraft(
            ObservationType(view.observation_type),
            ConfirmationState(view.confirmation_state),
            view.taxon_public_id,
            view.user_taxon_public_id,
            view.life_stage,
            view.sex,
            view.count,
            view.behavior,
            view.notes,
            view.roi_public_id,
        )
        self.state = ObservationEditorState(view.public_id, view.revision, draft)
        return self.state

    def commit(
        self, *, asset_public_id: str, public_id: str, now_us: int
    ) -> ObservationEditorState:
        try:
            view = (
                self._service.create(
                    public_id=public_id,
                    asset_public_id=asset_public_id,
                    draft=self.state.draft,
                    now_us=now_us,
                )
                if self.state.public_id is None
                else self._service.update(
                    public_id=self.state.public_id,
                    expected_revision=self.state.revision,
                    draft=self.state.draft,
                    now_us=now_us,
                )
            )
            return self.load(view)
        except Exception as exc:
            self.state = replace(self.state, error=str(exc))
            return self.state
