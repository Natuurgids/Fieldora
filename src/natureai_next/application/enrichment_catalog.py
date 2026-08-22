"""Canonical enrichment search, reporting and portable export."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from natureai_next.application.enrichment import CanonicalEnrichment, CanonicalEnrichmentService
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


@dataclass(frozen=True, slots=True)
class EnrichmentSearchQuery:
    text: str | None = None
    subject_type: str | None = None
    shape: str | None = None
    status: str | None = None
    source_id: str | None = None
    accepted_only: bool = False
    limit: int = 100


@dataclass(frozen=True, slots=True)
class EnrichmentReport:
    total: int
    by_status: dict[str, int]
    by_shape: dict[str, int]
    by_source: dict[str, int]


class EnrichmentCatalogService:
    def __init__(self, database_path: Path) -> None:
        self._factory = SqliteConnectionFactory(database_path)
        self._store = CanonicalEnrichmentService(database_path)

    def search(self, query: EnrichmentSearchQuery) -> tuple[CanonicalEnrichment, ...]:
        if query.limit < 1 or query.limit > 10_000:
            raise ValueError("search limit must be between 1 and 10000")
        clauses: list[str] = []
        parameters: list[Any] = []
        if query.subject_type:
            clauses.append("subject_type=?")
            parameters.append(query.subject_type)
        if query.shape:
            clauses.append("enrichment_type=?")
            parameters.append(query.shape)
        if query.status:
            clauses.append("status=?")
            parameters.append(query.status)
        elif query.accepted_only:
            clauses.append("status='accepted'")
        if query.source_id:
            clauses.append("source_id=?")
            parameters.append(query.source_id)
        if query.text:
            clauses.append("(summary LIKE ? ESCAPE '\\' OR payload_json LIKE ? ESCAPE '\\')")
            pattern = f"%{_escape_like(query.text)}%"
            parameters.extend((pattern, pattern))
        sql = "SELECT enrichment_id FROM enrichment_records"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at_us DESC,enrichment_id LIMIT ?"
        parameters.append(query.limit)
        connection = self._factory.connect(read_only=True)
        try:
            identifiers = [str(row[0]) for row in connection.execute(sql, parameters).fetchall()]
        finally:
            connection.close()
        return tuple(self._store.get(identifier) for identifier in identifiers)

    def report(self) -> EnrichmentReport:
        connection = self._factory.connect(read_only=True)
        try:
            total = int(connection.execute("SELECT COUNT(*) FROM enrichment_records").fetchone()[0])
            by_status = _counts(connection, "status")
            by_shape = _counts(connection, "enrichment_type")
            by_source = _counts(connection, "COALESCE(source_id,producer_id)")
            return EnrichmentReport(total, by_status, by_shape, by_source)
        finally:
            connection.close()

    def export_json(self, destination: Path, query: EnrichmentSearchQuery | None = None) -> Path:
        items = self.search(query or EnrichmentSearchQuery(limit=10_000))
        payload = {
            "format": "aperture-canonical-enrichment",
            "version": 1,
            "records": [_export_record(item) for item in items],
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return destination


def _counts(connection, expression: str) -> dict[str, int]:
    rows = connection.execute(
        f"SELECT {expression},COUNT(*) FROM enrichment_records GROUP BY {expression} ORDER BY {expression}"
    ).fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _export_record(item: CanonicalEnrichment) -> dict[str, Any]:
    return {
        "enrichment_id": item.enrichment_id,
        "subject": {"type": item.subject_type, "public_id": item.subject_public_id},
        "shape": item.enrichment_type,
        "status": item.status,
        "summary": item.summary,
        "confidence": item.confidence,
        "value": item.payload.get("value", {}),
        "target": item.payload.get("target", {}),
        "external_id": item.payload.get("external_id"),
        "source_snapshot": item.source_snapshot,
        "producer": {"id": item.producer_id, "version": item.producer_version},
        "created_at_us": item.created_at_us,
        "updated_at_us": item.updated_at_us,
        "reviewed_at_us": item.reviewed_at_us,
        "reviewer": item.reviewer,
    }
