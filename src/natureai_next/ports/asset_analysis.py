"""Persistence contract for immutable asset-analysis records."""

from __future__ import annotations

from typing import Protocol

from natureai_next.domain.ai import (
    AnalysisStatus,
    AnalysisTaxonCandidateRecord,
    AssetAnalysisRecord,
)


class AssetAnalysisRepository(Protocol):
    def create_analysis(self, record: AssetAnalysisRecord) -> int: ...

    def complete_analysis(
        self,
        public_id: str,
        *,
        status: AnalysisStatus,
        completed_at_us: int,
        result_summary_json: str,
    ) -> None: ...

    def add_taxon_candidate(
        self,
        record: AnalysisTaxonCandidateRecord,
        *,
        created_at_us: int,
    ) -> int: ...
