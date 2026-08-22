"""Persistence for immutable asset analyses and lightweight enrichment."""

from __future__ import annotations

from natureai_next.domain.ai import (
    AnalysisStatus,
    AnalysisTaxonCandidateRecord,
    AssetAnalysisRecord,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


class SqliteAssetAnalysisRepository:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def create_analysis(self, record: AssetAnalysisRecord) -> int:
        connection = self._factory.connect()
        try:
            asset = connection.execute(
                "SELECT id FROM assets WHERE public_id=?", (record.asset_public_id,)
            ).fetchone()
            if asset is None:
                raise KeyError(f"unknown asset: {record.asset_public_id}")
            cursor = connection.execute(
                "INSERT INTO asset_analyses(public_id,asset_id,engine_id,engine_family,model_name,model_version,analysis_kind,status,configuration_json,configuration_hash,result_summary_json,source_sha256,application_version,started_at_us,completed_at_us,created_at_us) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.public_id,
                    int(asset[0]),
                    record.engine_id,
                    record.engine_family,
                    record.model_name,
                    record.model_version,
                    record.analysis_kind,
                    record.status.value,
                    record.configuration_json,
                    record.configuration_hash,
                    record.result_summary_json,
                    record.source_sha256,
                    record.application_version,
                    record.started_at_us,
                    record.completed_at_us,
                    record.created_at_us,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)
        finally:
            connection.close()

    def complete_analysis(
        self,
        public_id: str,
        *,
        status: AnalysisStatus,
        completed_at_us: int,
        result_summary_json: str,
    ) -> None:
        if status is AnalysisStatus.RUNNING:
            raise ValueError("completed analysis cannot remain running")
        connection = self._factory.connect()
        try:
            cursor = connection.execute(
                "UPDATE asset_analyses SET status=?,completed_at_us=?,result_summary_json=? WHERE public_id=? AND status='running'",
                (status.value, completed_at_us, result_summary_json, public_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"running analysis not found: {public_id}")
            connection.commit()
        finally:
            connection.close()

    def add_taxon_candidate(
        self, record: AnalysisTaxonCandidateRecord, *, created_at_us: int
    ) -> int:
        connection = self._factory.connect()
        try:
            analysis = connection.execute(
                "SELECT id FROM asset_analyses WHERE public_id=?", (record.analysis_public_id,)
            ).fetchone()
            if analysis is None:
                raise KeyError(f"unknown analysis: {record.analysis_public_id}")
            local_taxon_id = None
            if record.local_taxon_public_id is not None:
                taxon = connection.execute(
                    "SELECT id FROM taxa WHERE public_id=?", (record.local_taxon_public_id,)
                ).fetchone()
                if taxon is None:
                    raise KeyError(f"unknown local taxon: {record.local_taxon_public_id}")
                local_taxon_id = int(taxon[0])
            cursor = connection.execute(
                "INSERT INTO analysis_taxon_candidates(public_id,analysis_id,local_taxon_id,reference_taxon_public_id,model_label,rank,raw_score,calibrated_score,confidence_band,taxonomic_level,provenance_json,created_at_us) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.public_id,
                    int(analysis[0]),
                    local_taxon_id,
                    record.reference_taxon_public_id,
                    record.model_label,
                    record.rank,
                    record.raw_score,
                    record.calibrated_score,
                    record.confidence_band.value,
                    record.taxonomic_level,
                    record.provenance_json,
                    created_at_us,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)
        finally:
            connection.close()

    def list_for_asset(self, asset_public_id: str) -> tuple[AssetAnalysisRecord, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT x.public_id,a.public_id,x.engine_id,x.engine_family,x.model_name,x.model_version,x.analysis_kind,x.status,x.configuration_json,x.configuration_hash,x.result_summary_json,x.source_sha256,x.application_version,x.started_at_us,x.completed_at_us,x.created_at_us FROM asset_analyses x JOIN assets a ON a.id=x.asset_id WHERE a.public_id=? ORDER BY x.created_at_us DESC,x.id DESC",
                (asset_public_id,),
            ).fetchall()
            return tuple(
                AssetAnalysisRecord(
                    str(r[0]),
                    str(r[1]),
                    str(r[2]),
                    str(r[3]),
                    None if r[4] is None else str(r[4]),
                    None if r[5] is None else str(r[5]),
                    str(r[6]),
                    AnalysisStatus(str(r[7])),
                    str(r[8]),
                    str(r[9]),
                    str(r[10]),
                    None if r[11] is None else str(r[11]),
                    str(r[12]),
                    int(r[13]),
                    None if r[14] is None else int(r[14]),
                    int(r[15]),
                )
                for r in rows
            )
        finally:
            connection.close()

    def list_candidates_for_asset(self, asset_public_id: str):
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                """SELECT c.public_id,x.public_id,c.model_label,c.rank,c.raw_score,c.calibrated_score,
                          c.confidence_band,c.reference_taxon_public_id,t.public_id,c.taxonomic_level,c.provenance_json
                   FROM analysis_taxon_candidates c
                   JOIN asset_analyses x ON x.id=c.analysis_id
                   JOIN assets a ON a.id=x.asset_id
                   LEFT JOIN taxa t ON t.id=c.local_taxon_id
                   WHERE a.public_id=?
                   ORDER BY x.created_at_us DESC,c.rank,c.id""",
                (asset_public_id,),
            ).fetchall()
            return tuple(
                {
                    "public_id": str(r[0]),
                    "analysis_public_id": str(r[1]),
                    "model_label": str(r[2]),
                    "rank": int(r[3]),
                    "raw_score": float(r[4]),
                    "calibrated_score": None if r[5] is None else float(r[5]),
                    "confidence_band": str(r[6]),
                    "reference_taxon_public_id": None if r[7] is None else str(r[7]),
                    "local_taxon_public_id": None if r[8] is None else str(r[8]),
                    "taxonomic_level": None if r[9] is None else str(r[9]),
                    "provenance_json": str(r[10]),
                }
                for r in rows
            )
        finally:
            connection.close()

    def promote_to_observation(
        self,
        *,
        public_id: str,
        analysis_public_id: str,
        candidate_public_id: str | None,
        observation_public_id: str,
        state: str,
        actor: str,
        reason: str | None,
        created_at_us: int,
    ) -> None:
        if state not in {"accepted", "rejected", "superseded"}:
            raise ValueError("invalid promotion state")
        connection = self._factory.connect()
        try:
            analysis = connection.execute(
                "SELECT id FROM asset_analyses WHERE public_id=?", (analysis_public_id,)
            ).fetchone()
            observation = connection.execute(
                "SELECT id FROM observations WHERE public_id=?", (observation_public_id,)
            ).fetchone()
            if analysis is None or observation is None:
                raise KeyError("analysis or observation not found")
            candidate_id = None
            if candidate_public_id is not None:
                candidate = connection.execute(
                    "SELECT id,analysis_id FROM analysis_taxon_candidates WHERE public_id=?",
                    (candidate_public_id,),
                ).fetchone()
                if candidate is None or int(candidate[1]) != int(analysis[0]):
                    raise KeyError("candidate does not belong to analysis")
                candidate_id = int(candidate[0])
            connection.execute(
                "INSERT INTO analysis_observation_promotions(public_id,analysis_id,candidate_id,observation_id,promotion_state,actor,reason,created_at_us) VALUES(?,?,?,?,?,?,?,?)",
                (
                    public_id,
                    int(analysis[0]),
                    candidate_id,
                    int(observation[0]),
                    state,
                    actor,
                    reason,
                    created_at_us,
                ),
            )
            connection.commit()
        finally:
            connection.close()
