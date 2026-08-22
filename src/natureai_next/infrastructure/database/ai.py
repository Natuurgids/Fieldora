"""SQLite model registry, embedding persistence, and exact vector search."""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass

from natureai_next.domain.ai import EmbeddingVector, SimilarityMatch
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


@dataclass(frozen=True, slots=True)
class ActiveModelVariant:
    id: int
    public_id: str
    model_identity: str
    variant_identity: str
    install_path_token: str
    artifact_relative_path: str
    runtime: str
    precision: str
    preprocessing_identity: str
    embedding_dimension: int
    input_size: int


class SqliteAIRepository:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def active_variant(self, model_identity: str) -> ActiveModelVariant | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT v.id,v.public_id,p.model_identity,v.variant_identity,p.install_path_token,v.artifact_relative_path,v.runtime,v.precision,v.preprocessing_identity,v.embedding_dimension,v.input_size FROM model_variants v JOIN model_packages p ON p.id=v.package_id WHERE p.model_identity=? AND p.active=1 AND v.active=1 ORDER BY p.activated_at_us DESC,v.id LIMIT 1",
                (model_identity,),
            ).fetchone()
            return None if row is None else ActiveModelVariant(*row)
        finally:
            connection.close()

    def store_embedding(
        self,
        *,
        asset_public_id: str,
        model_variant_id: int,
        preprocessing_identity: str,
        vector: EmbeddingVector,
        source_sha256: str | None,
        execution_provider: str,
        precision: str,
        application_version: str,
        inference_run_id: int | None = None,
    ) -> None:
        normalized = vector.normalized()
        blob = normalized.to_blob()
        checksum = hashlib.sha256(blob).hexdigest()
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            asset = connection.execute(
                "SELECT id FROM assets WHERE public_id=?", (asset_public_id,)
            ).fetchone()
            if asset is None:
                raise KeyError(f"unknown asset: {asset_public_id}")
            connection.execute(
                "INSERT INTO embeddings(asset_id,model_variant_id,preprocessing_identity,region_of_interest_id,vector_dimension,scalar_type,normalized,vector_blob,vector_checksum,created_at_us,source_sha256,execution_provider,precision,application_version,inference_run_id,validity_state) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(asset_id,model_variant_id,preprocessing_identity,region_of_interest_id) DO UPDATE SET vector_dimension=excluded.vector_dimension,scalar_type=excluded.scalar_type,normalized=excluded.normalized,vector_blob=excluded.vector_blob,vector_checksum=excluded.vector_checksum,created_at_us=excluded.created_at_us,source_sha256=excluded.source_sha256,execution_provider=excluded.execution_provider,precision=excluded.precision,application_version=excluded.application_version,inference_run_id=excluded.inference_run_id,validity_state='valid'",
                (
                    int(asset[0]),
                    model_variant_id,
                    preprocessing_identity,
                    None,
                    normalized.dimension,
                    "float32",
                    1,
                    blob,
                    checksum,
                    time.time_ns() // 1000,
                    source_sha256,
                    execution_provider,
                    precision,
                    application_version,
                    inference_run_id,
                    "valid",
                ),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def find_missing_or_stale(
        self, model_variant_id: int, preprocessing_identity: str, limit: int = 1000
    ) -> tuple[str, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT a.public_id FROM assets a LEFT JOIN embeddings e ON e.asset_id=a.id AND e.model_variant_id=? AND e.preprocessing_identity=? AND e.region_of_interest_id IS NULL WHERE a.lifecycle_state='active' AND (e.id IS NULL OR e.validity_state!='valid' OR (e.source_sha256 IS NOT NULL AND e.source_sha256<>COALESCE((SELECT f.sha256 FROM file_instances f WHERE f.id=a.primary_file_instance_id),''))) ORDER BY a.id LIMIT ?",
                (model_variant_id, preprocessing_identity, max(1, min(limit, 10000))),
            ).fetchall()
            return tuple(str(row[0]) for row in rows)
        finally:
            connection.close()

    def exact_search(
        self,
        model_variant_id: int,
        preprocessing_identity: str,
        query: EmbeddingVector,
        limit: int = 50,
    ) -> tuple[SimilarityMatch, ...]:
        normalized_query = query.normalized()
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT a.public_id,e.vector_blob,e.vector_dimension,e.vector_checksum FROM embeddings e JOIN assets a ON a.id=e.asset_id WHERE e.model_variant_id=? AND e.preprocessing_identity=? AND e.validity_state='valid' AND a.lifecycle_state='active'",
                (model_variant_id, preprocessing_identity),
            ).fetchall()
        finally:
            connection.close()
        matches: list[SimilarityMatch] = []
        for row in rows:
            blob = bytes(row[1])
            if hashlib.sha256(blob).hexdigest() != str(row[3]):
                continue
            vector = EmbeddingVector.from_blob(blob, int(row[2]))
            if vector.dimension != normalized_query.dimension:
                continue
            score = math.fsum(
                a * b for a, b in zip(normalized_query.values, vector.values, strict=True)
            )
            matches.append(SimilarityMatch(str(row[0]), score))
        matches.sort(key=lambda item: (-item.score, item.asset_public_id))
        return tuple(matches[: max(1, min(limit, 1000))])

    def begin_inference_run(
        self,
        *,
        public_id: str,
        model_variant_id: int,
        execution_provider: str,
        precision: str,
        application_version: str,
        requested_item_count: int,
        parameters_json: str = "{}",
        job_public_id: str | None = None,
    ) -> int:
        connection = self._factory.connect()
        try:
            job_id = None
            if job_public_id is not None:
                row = connection.execute(
                    "SELECT id FROM jobs WHERE public_id=?", (job_public_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(f"unknown job: {job_public_id}")
                job_id = int(row[0])
            cursor = connection.execute(
                "INSERT INTO inference_runs(public_id,job_id,model_variant_id,execution_provider,parameter_json,application_version,started_at_us,outcome,error_code,precision,requested_item_count,completed_item_count,failed_item_count,retry_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    public_id,
                    job_id,
                    model_variant_id,
                    execution_provider,
                    parameters_json,
                    application_version,
                    time.time_ns() // 1000,
                    "running",
                    None,
                    precision,
                    requested_item_count,
                    0,
                    0,
                    0,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)
        finally:
            connection.close()

    def finish_inference_run(
        self,
        run_id: int,
        *,
        completed: int,
        failed: int,
        retries: int,
        final_batch_size: int,
        error_text: str | None = None,
    ) -> None:
        outcome = "succeeded" if failed == 0 and error_text is None else "completed_with_errors"
        connection = self._factory.connect()
        try:
            connection.execute(
                "UPDATE inference_runs SET completed_at_us=?,outcome=?,completed_item_count=?,failed_item_count=?,retry_count=?,final_batch_size=?,error_text=? WHERE id=?",
                (
                    time.time_ns() // 1000,
                    outcome,
                    completed,
                    failed,
                    retries,
                    final_batch_size,
                    error_text,
                    run_id,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def load_vectors(
        self, model_variant_id: int, preprocessing_identity: str
    ) -> dict[str, EmbeddingVector]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT a.public_id,e.vector_blob,e.vector_dimension,e.vector_checksum FROM embeddings e JOIN assets a ON a.id=e.asset_id WHERE e.model_variant_id=? AND e.preprocessing_identity=? AND e.validity_state='valid' AND a.lifecycle_state='active' ORDER BY a.id",
                (model_variant_id, preprocessing_identity),
            ).fetchall()
        finally:
            connection.close()
        vectors: dict[str, EmbeddingVector] = {}
        for row in rows:
            blob = bytes(row[1])
            if hashlib.sha256(blob).hexdigest() == str(row[3]):
                vectors[str(row[0])] = EmbeddingVector.from_blob(blob, int(row[2]))
        return vectors

    def audit_embeddings(
        self, model_variant_id: int, preprocessing_identity: str
    ) -> tuple[int, int]:
        connection = self._factory.connect()
        checked = corrupt = 0
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT id,vector_blob,vector_checksum,vector_dimension FROM embeddings WHERE model_variant_id=? AND preprocessing_identity=?",
                (model_variant_id, preprocessing_identity),
            ).fetchall()
            for row in rows:
                checked += 1
                blob = bytes(row[1])
                valid = len(blob) == int(row[3]) * 4 and hashlib.sha256(blob).hexdigest() == str(
                    row[2]
                )
                if not valid:
                    corrupt += 1
                    connection.execute(
                        "UPDATE embeddings SET validity_state='corrupt' WHERE id=?", (int(row[0]),)
                    )
            connection.execute("COMMIT")
            return checked, corrupt
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def register_index_generation(
        self,
        *,
        public_id: str,
        model_variant_id: int,
        preprocessing_identity: str,
        generation: str,
        path_token: str,
        manifest_json: str,
        checksum: str,
        source_row_count: int,
        backend: str,
    ) -> int:
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE vector_index_generations SET state='superseded' WHERE model_variant_id=? AND preprocessing_identity=? AND state='active'",
                (model_variant_id, preprocessing_identity),
            )
            cursor = connection.execute(
                "INSERT INTO vector_index_generations(public_id,model_variant_id,preprocessing_identity,metric,generation,index_path_token,manifest_json,index_checksum,source_row_count,state,created_at_us,activated_at_us,backend,validated_at_us) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    public_id,
                    model_variant_id,
                    preprocessing_identity,
                    "cosine",
                    generation,
                    path_token,
                    manifest_json,
                    checksum,
                    source_row_count,
                    "active",
                    time.time_ns() // 1000,
                    time.time_ns() // 1000,
                    backend,
                    time.time_ns() // 1000,
                ),
            )
            connection.execute("COMMIT")
            return int(cursor.lastrowid)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def mark_index_corrupt(self, index_id: int, error: str) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "UPDATE vector_index_generations SET state='corrupt',validation_error=?,validated_at_us=? WHERE id=?",
                (error[:2000], time.time_ns() // 1000, index_id),
            )
            connection.commit()
        finally:
            connection.close()
