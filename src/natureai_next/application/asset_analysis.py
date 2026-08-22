"""Application boundary for immutable photo enrichment records."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from natureai_next import __version__
from natureai_next.domain.ai import (
    AnalysisStatus,
    AnalysisTaxonCandidateRecord,
    AssetAnalysisRecord,
    ConfidenceBand,
)
from natureai_next.ports.asset_analysis import AssetAnalysisRepository


@dataclass(frozen=True, slots=True)
class TaxonCandidateInput:
    label: str
    rank: int
    raw_score: float
    calibrated_score: float | None = None
    confidence_band: ConfidenceBand = ConfidenceBand.UNCLASSIFIED
    local_taxon_public_id: str | None = None
    reference_taxon_public_id: str | None = None
    taxonomic_level: str | None = None
    provenance: Mapping[str, object] | None = None


class AssetAnalysisService:
    def __init__(self, repository: AssetAnalysisRepository) -> None:
        self._repository = repository

    def start(
        self,
        *,
        asset_public_id: str,
        engine_id: str,
        engine_family: str,
        analysis_kind: str,
        model_name: str | None = None,
        model_version: str | None = None,
        configuration: Mapping[str, object] | None = None,
        source_sha256: str | None = None,
    ) -> str:
        configuration_json = json.dumps(configuration or {}, sort_keys=True, separators=(",", ":"))
        now = time.time_ns() // 1000
        public_id = f"analysis-{uuid.uuid4()}"
        self._repository.create_analysis(
            AssetAnalysisRecord(
                public_id,
                asset_public_id,
                engine_id,
                engine_family,
                model_name,
                model_version,
                analysis_kind,
                AnalysisStatus.RUNNING,
                configuration_json,
                hashlib.sha256(configuration_json.encode()).hexdigest(),
                "{}",
                source_sha256,
                __version__,
                now,
                None,
                now,
            )
        )
        return public_id

    def complete(
        self,
        analysis_public_id: str,
        *,
        status: AnalysisStatus = AnalysisStatus.SUCCEEDED,
        summary: Mapping[str, object] | None = None,
        candidates: Sequence[TaxonCandidateInput] = (),
    ) -> None:
        now = time.time_ns() // 1000
        for candidate in candidates:
            self._repository.add_taxon_candidate(
                AnalysisTaxonCandidateRecord(
                    public_id=f"candidate-{uuid.uuid4()}",
                    analysis_public_id=analysis_public_id,
                    model_label=candidate.label,
                    rank=candidate.rank,
                    raw_score=candidate.raw_score,
                    calibrated_score=candidate.calibrated_score,
                    confidence_band=candidate.confidence_band,
                    local_taxon_public_id=candidate.local_taxon_public_id,
                    reference_taxon_public_id=candidate.reference_taxon_public_id,
                    taxonomic_level=candidate.taxonomic_level,
                    provenance_json=json.dumps(candidate.provenance or {}, sort_keys=True),
                ),
                created_at_us=now,
            )
        self._repository.complete_analysis(
            analysis_public_id,
            status=status,
            completed_at_us=now,
            result_summary_json=json.dumps(summary or {}, sort_keys=True),
        )
