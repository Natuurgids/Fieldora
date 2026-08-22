"""Stable application ports for AI suggestion generation and review."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from natureai_next.domain.ai import (
    EmbeddingVector,
    PromptSetManifest,
    PromptSetRecord,
    ReviewBatchResult,
    SuggestionCandidate,
    SuggestionDetail,
    SuggestionPage,
    TaxonomyEmbeddingRefreshPlan,
    TaxonomyTextLabel,
)


class PromptSetLoader(Protocol):
    def __call__(self, path: Path) -> PromptSetManifest: ...


class PromptSetStore(Protocol):
    def install(
        self,
        manifest: PromptSetManifest,
        *,
        checksum: str,
        public_id: str,
        now_us: int,
        activate: bool,
    ) -> PromptSetRecord: ...

    def activate(self, public_id: str, *, now_us: int) -> PromptSetRecord: ...

    def list(self, identity: str | None = None) -> tuple[PromptSetRecord, ...]: ...

    def active_for_model_family(self, model_family: str) -> PromptSetRecord | None: ...


class SuggestionStore(Protocol):
    def create_suggestions(self, **kwargs: object) -> tuple[str, ...]: ...

    def page(self, **kwargs: object) -> SuggestionPage: ...

    def page_for_asset(self, asset_public_id: str, **kwargs: object) -> SuggestionPage: ...

    def reject_other_suggestions(
        self,
        suggestion_public_id: str,
        *,
        action_id_factory: Callable[[], str],
        now_us: int,
        reason: str | None = None,
    ) -> ReviewBatchResult: ...

    def accept_and_reject_others(
        self,
        suggestion_public_id: str,
        *,
        action_id_factory: Callable[[], str],
        now_us: int,
    ) -> ReviewBatchResult: ...

    def accept_all_pending_for_asset(
        self,
        suggestion_public_id: str,
        *,
        action_id_factory: Callable[[], str],
        now_us: int,
    ) -> ReviewBatchResult: ...

    def detail(
        self, suggestion_public_id: str, *, region_code: str | None = None
    ) -> SuggestionDetail: ...

    def review(self, **kwargs: object) -> None: ...

    def assign_review(self, **kwargs: object) -> None: ...

    def batch_review(
        self,
        suggestion_public_ids: Sequence[str],
        *,
        action: str,
        action_id_factory: Callable[[], str],
        now_us: int,
        reason: str | None = None,
    ) -> ReviewBatchResult: ...

    def supersede(
        self,
        old_suggestion_public_id: str,
        new_suggestion_public_id: str,
        *,
        action_public_id: str,
        now_us: int,
        reason: str | None = None,
    ) -> None: ...

    def reverse_acceptance(self, **kwargs: object) -> None: ...

    def overview(self) -> object: ...


class CandidateRanker(Protocol):
    def rank(
        self,
        image: EmbeddingVector,
        candidates: Sequence[tuple[str, str, EmbeddingVector]],
        *,
        region_code: str | None,
        limit: int,
    ) -> tuple[SuggestionCandidate, ...]: ...


class TaxonomyEmbeddingStore(Protocol):
    def replace_generation(self, **kwargs: object) -> int: ...
    def candidates(self, **kwargs: object) -> tuple[tuple[str, str, EmbeddingVector], ...]: ...
    def invalidate(self, **kwargs: object) -> int: ...


class NearDuplicateStore(Protocol):
    def replace_groups(self, **kwargs: object) -> tuple[str, ...]: ...
    def page_groups(self, **kwargs: object) -> tuple[object, ...]: ...


class ReviewSessionStore(Protocol):
    def load(self) -> str | None: ...
    def save(self, state_json: str, *, public_id: str, now_us: int) -> None: ...


class TaxonomyLabelSource(Protocol):
    def active_release_ids(self) -> tuple[str, ...]: ...

    def active_labels(
        self,
        *,
        language_tags: Sequence[str] = (),
        region_codes: Sequence[str] = (),
        include_synonyms: bool = True,
    ) -> tuple[TaxonomyTextLabel, ...]: ...


class TaxonomyEmbeddingRefreshPlanSource(Protocol):
    def active_plans(self) -> tuple[TaxonomyEmbeddingRefreshPlan, ...]: ...
