"""Canonical Aperture enrichment service independent from producer plugins."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from natureai_next.domain.enrichment import EnrichmentStatus
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


@dataclass(frozen=True, slots=True)
class EnrichmentValue:
    key: str
    value: Any
    value_type: str
    ordinal: int = 0
    unit: str | None = None
    language_code: str | None = None
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class EnrichmentLabel:
    namespace: str
    key: str
    display_value: str | None = None
    ordinal: int = 0
    confidence: float | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalEnrichment:
    enrichment_id: str
    subject_type: str
    subject_public_id: str
    enrichment_type: str
    producer_id: str
    schema_version: int = 1
    producer_version: str | None = None
    producer_run_id: str | None = None
    status: str = EnrichmentStatus.GENERATED.value
    confidence: float | None = None
    summary: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] | None = None
    values: tuple[EnrichmentValue, ...] = ()
    labels: tuple[EnrichmentLabel, ...] = ()
    source_id: str | None = None
    source_snapshot: dict[str, Any] = field(default_factory=dict)
    created_at_us: int | None = None
    updated_at_us: int | None = None
    reviewed_at_us: int | None = None
    reviewer: str | None = None


class CanonicalEnrichmentService:
    def __init__(self, database_path: Path) -> None:
        self._factory = SqliteConnectionFactory(database_path)

    def store(self, item: CanonicalEnrichment) -> None:
        now = time.time_ns() // 1000
        created_at = item.created_at_us or now
        updated_at = item.updated_at_us or now
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO enrichment_records(
                    enrichment_id,subject_type,subject_public_id,enrichment_type,schema_version,
                    producer_id,producer_version,producer_run_id,status,confidence,summary,
                    payload_json,evidence_json,source_id,source_snapshot_json,
                    created_at_us,updated_at_us,reviewed_at_us,reviewer
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(enrichment_id) DO UPDATE SET
                    status=excluded.status,confidence=excluded.confidence,summary=excluded.summary,
                    payload_json=excluded.payload_json,evidence_json=excluded.evidence_json,
                    source_id=excluded.source_id,source_snapshot_json=excluded.source_snapshot_json,
                    updated_at_us=excluded.updated_at_us,reviewed_at_us=excluded.reviewed_at_us,
                    reviewer=excluded.reviewer""",
                (
                    item.enrichment_id,
                    item.subject_type,
                    item.subject_public_id,
                    item.enrichment_type,
                    item.schema_version,
                    item.producer_id,
                    item.producer_version,
                    item.producer_run_id,
                    item.status,
                    item.confidence,
                    item.summary,
                    json.dumps(item.payload, separators=(",", ":")),
                    None
                    if item.evidence is None
                    else json.dumps(item.evidence, separators=(",", ":")),
                    item.source_id or item.producer_id,
                    json.dumps(item.source_snapshot, separators=(",", ":")),
                    created_at,
                    updated_at,
                    item.reviewed_at_us,
                    item.reviewer,
                ),
            )
            connection.execute(
                "DELETE FROM enrichment_values WHERE enrichment_id=?", (item.enrichment_id,)
            )
            connection.execute(
                "DELETE FROM enrichment_labels WHERE enrichment_id=?", (item.enrichment_id,)
            )
            for value in item.values:
                columns = {
                    "text": "text_value",
                    "integer": "integer_value",
                    "real": "real_value",
                    "boolean": "boolean_value",
                    "timestamp": "timestamp_value_us",
                    "reference": "reference_value",
                    "json": "json_value",
                }
                if value.value_type not in columns:
                    raise ValueError(f"unsupported enrichment value type: {value.value_type}")
                stored = {name: None for name in columns.values()}
                raw = (
                    json.dumps(value.value, separators=(",", ":"))
                    if value.value_type == "json"
                    else value.value
                )
                stored[columns[value.value_type]] = raw
                connection.execute(
                    """INSERT INTO enrichment_values(
                        enrichment_id,field_key,value_ordinal,value_type,text_value,
                        integer_value,real_value,boolean_value,timestamp_value_us,
                        reference_value,json_value,unit,language_code,confidence
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        item.enrichment_id,
                        value.key,
                        value.ordinal,
                        value.value_type,
                        stored["text_value"],
                        stored["integer_value"],
                        stored["real_value"],
                        stored["boolean_value"],
                        stored["timestamp_value_us"],
                        stored["reference_value"],
                        stored["json_value"],
                        value.unit,
                        value.language_code,
                        value.confidence,
                    ),
                )
            connection.executemany(
                """INSERT INTO enrichment_labels(
                    enrichment_id,label_namespace,label_key,display_value,
                    value_ordinal,confidence,source
                ) VALUES(?,?,?,?,?,?,?)""",
                [
                    (
                        item.enrichment_id,
                        label.namespace,
                        label.key,
                        label.display_value,
                        label.ordinal,
                        label.confidence,
                        label.source,
                    )
                    for label in item.labels
                ],
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get(self, enrichment_id: str) -> CanonicalEnrichment:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT * FROM enrichment_records WHERE enrichment_id=?", (enrichment_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown enrichment: {enrichment_id}")
            return _record_from_row(row)
        finally:
            connection.close()

    def list_for_subject(
        self,
        subject_type: str,
        subject_public_id: str,
        *,
        include_rejected: bool = False,
    ) -> tuple[CanonicalEnrichment, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            sql = "SELECT * FROM enrichment_records WHERE subject_type=? AND subject_public_id=?"
            parameters: list[object] = [subject_type, subject_public_id]
            if not include_rejected:
                sql += " AND status!='rejected'"
            sql += " ORDER BY created_at_us,enrichment_id"
            rows = connection.execute(sql, parameters).fetchall()
            return tuple(_record_from_row(row) for row in rows)
        finally:
            connection.close()

    def review(
        self,
        enrichment_id: str,
        status: EnrichmentStatus,
        *,
        reviewer: str,
        reviewed_at_us: int | None = None,
    ) -> CanonicalEnrichment:
        if status not in {EnrichmentStatus.ACCEPTED, EnrichmentStatus.REJECTED}:
            raise ValueError("review status must be accepted or rejected")
        now = reviewed_at_us or time.time_ns() // 1000
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM enrichment_records WHERE enrichment_id=?", (enrichment_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown enrichment: {enrichment_id}")
            if str(row[0]) in {
                EnrichmentStatus.SUPERSEDED.value,
                EnrichmentStatus.EXPIRED.value,
            }:
                raise ValueError("superseded or expired enrichment cannot be reviewed")
            connection.execute(
                """UPDATE enrichment_records
                   SET status=?,reviewed_at_us=?,reviewer=?,updated_at_us=?
                   WHERE enrichment_id=?""",
                (status.value, now, reviewer, now, enrichment_id),
            )
            connection.execute(
                """INSERT INTO enrichment_review_events(
                    enrichment_id,status,reviewer,reviewed_at_us
                ) VALUES(?,?,?,?)""",
                (enrichment_id, status.value, reviewer, now),
            )
            assignment = connection.execute(
                "SELECT assigned_to FROM enrichment_review_assignments WHERE enrichment_id=?",
                (enrichment_id,),
            ).fetchone()
            if assignment is not None:
                connection.execute(
                    """INSERT INTO enrichment_review_assignment_events(
                        enrichment_id,assigned_to,assigned_by,action,note,created_at_us
                    ) VALUES(?,?,?,?,?,?)""",
                    (enrichment_id, str(assignment[0]), reviewer, "completed", "", now),
                )
                connection.execute(
                    "DELETE FROM enrichment_review_assignments WHERE enrichment_id=?",
                    (enrichment_id,),
                )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return self.get(enrichment_id)

    def assign_review(
        self,
        enrichment_id: str,
        *,
        assigned_to: str | None,
        assigned_by: str,
        note: str = "",
        assigned_at_us: int | None = None,
    ) -> None:
        """Assign or return a canonical review without changing its evidence state."""
        actor = assigned_by.strip()
        target = "" if assigned_to is None else assigned_to.strip()
        if not actor:
            raise ValueError("assigned_by must not be blank")
        now = assigned_at_us or time.time_ns() // 1000
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            record = connection.execute(
                "SELECT status FROM enrichment_records WHERE enrichment_id=?",
                (enrichment_id,),
            ).fetchone()
            if record is None:
                raise KeyError(f"unknown enrichment: {enrichment_id}")
            if str(record[0]) not in {
                EnrichmentStatus.GENERATED.value,
                EnrichmentStatus.PENDING_REVIEW.value,
            }:
                raise ValueError("only generated or pending enrichment can be assigned")
            previous = connection.execute(
                "SELECT assigned_to FROM enrichment_review_assignments WHERE enrichment_id=?",
                (enrichment_id,),
            ).fetchone()
            if target:
                connection.execute(
                    """INSERT INTO enrichment_review_assignments(
                        enrichment_id,assigned_to,assigned_by,assigned_at_us,note
                    ) VALUES(?,?,?,?,?)
                    ON CONFLICT(enrichment_id) DO UPDATE SET
                        assigned_to=excluded.assigned_to,
                        assigned_by=excluded.assigned_by,
                        assigned_at_us=excluded.assigned_at_us,
                        note=excluded.note""",
                    (enrichment_id, target, actor, now, note.strip()),
                )
                action = "reassigned" if previous is not None else "assigned"
            else:
                connection.execute(
                    "DELETE FROM enrichment_review_assignments WHERE enrichment_id=?",
                    (enrichment_id,),
                )
                action = "unassigned"
            connection.execute(
                """INSERT INTO enrichment_review_assignment_events(
                    enrichment_id,assigned_to,assigned_by,action,note,created_at_us
                ) VALUES(?,?,?,?,?,?)""",
                (enrichment_id, target or None, actor, action, note.strip(), now),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


def _record_from_row(row: Any) -> CanonicalEnrichment:
    return CanonicalEnrichment(
        enrichment_id=str(row["enrichment_id"]),
        subject_type=str(row["subject_type"]),
        subject_public_id=str(row["subject_public_id"]),
        enrichment_type=str(row["enrichment_type"]),
        schema_version=int(row["schema_version"]),
        producer_id=str(row["producer_id"]),
        producer_version=None if row["producer_version"] is None else str(row["producer_version"]),
        producer_run_id=None if row["producer_run_id"] is None else str(row["producer_run_id"]),
        status=str(row["status"]),
        confidence=None if row["confidence"] is None else float(row["confidence"]),
        summary=None if row["summary"] is None else str(row["summary"]),
        payload=json.loads(str(row["payload_json"])),
        evidence=None if row["evidence_json"] is None else json.loads(str(row["evidence_json"])),
        source_id=None if row["source_id"] is None else str(row["source_id"]),
        source_snapshot=json.loads(str(row["source_snapshot_json"] or "{}")),
        created_at_us=int(row["created_at_us"]),
        updated_at_us=int(row["updated_at_us"]),
        reviewed_at_us=None if row["reviewed_at_us"] is None else int(row["reviewed_at_us"]),
        reviewer=None if row["reviewer"] is None else str(row["reviewer"]),
    )
