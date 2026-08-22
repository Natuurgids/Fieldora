"""Suggestion-generation query contracts."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from natureai_next.domain.ai import ActiveAIContext, EmbeddingVector


class SuggestionGenerationSource(Protocol):
    def active_context(self) -> ActiveAIContext: ...
    def asset_paths(self, public_ids: Sequence[str]) -> tuple[tuple[str, Path], ...]: ...


class TaxonomyCandidateSource(Protocol):
    def candidates(
        self,
        *,
        model_variant_id: int,
        preprocessing_identity: str,
        broad_group: str | None = None,
        region_code: str | None = None,
    ) -> tuple[tuple[str, str, EmbeddingVector], ...]: ...
