"""PostgreSQL metadata repository for governed project exports."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from natureai_next.server.exports import GovernedExport

_COLUMNS = (
    "export_id,job_id,subject_id,organization_id,project_id,filename,"
    "relative_path,size_bytes,sha256,created_at_utc,expires_at_utc,"
    "revoked_at_utc,purged_at_utc,signing_key_id,signature_base64"
)


class PostgresExportMetadataRepository:
    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS governed_exports(
                        export_id TEXT PRIMARY KEY,
                        job_id TEXT NOT NULL UNIQUE,
                        subject_id TEXT NOT NULL,
                        organization_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        relative_path TEXT NOT NULL UNIQUE,
                        size_bytes BIGINT NOT NULL CHECK(size_bytes >= 0),
                        sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
                        created_at_utc TIMESTAMPTZ NOT NULL,
                        expires_at_utc TIMESTAMPTZ NOT NULL,
                        revoked_at_utc TIMESTAMPTZ,
                        purged_at_utc TIMESTAMPTZ,
                        signing_key_id TEXT NOT NULL DEFAULT '',
                        signature_base64 TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_governed_exports_expiry_pg "
                    "ON governed_exports(purged_at_utc,expires_at_utc,export_id)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_governed_exports_scope_pg "
                    "ON governed_exports(organization_id,project_id,export_id)"
                )

    def insert(self, record: GovernedExport) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO governed_exports({_COLUMNS}) VALUES("
                    "%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL,%s,%s)",
                    (
                        record.export_id, record.job_id, record.subject_id,
                        record.organization_id, record.project_id, record.filename,
                        record.relative_path, record.size_bytes, record.sha256,
                        record.created_at_utc, record.expires_at_utc,
                        record.signing_key_id, record.signature_base64,
                    ),
                )

    def stored(self, export_id: str) -> GovernedExport | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT {_COLUMNS} FROM governed_exports WHERE export_id=%s",
                    (export_id,),
                )
                row = cursor.fetchone()
        return None if row is None else self._decode(row)

    def revoke(self, export_id: str, at_utc: str) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE governed_exports SET revoked_at_utc=%s "
                    "WHERE export_id=%s AND revoked_at_utc IS NULL "
                    "AND purged_at_utc IS NULL",
                    (at_utc, export_id),
                )
                return cursor.rowcount == 1

    def attach_attestation(
        self, export_id: str, key_id: str, signature_base64: str
    ) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE governed_exports SET signing_key_id=%s,"
                    "signature_base64=%s WHERE export_id=%s AND signing_key_id='' "
                    "AND revoked_at_utc IS NULL AND purged_at_utc IS NULL",
                    (key_id, signature_base64, export_id),
                )
                return cursor.rowcount == 1

    def claim_expired(
        self, cutoff_utc: str, limit: int = 1000
    ) -> tuple[GovernedExport, ...]:
        bounded = max(1, min(limit, 1000))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "WITH candidates AS ("
                    " SELECT export_id FROM governed_exports"
                    " WHERE purged_at_utc IS NULL AND "
                    " (revoked_at_utc IS NOT NULL OR expires_at_utc<=%s)"
                    " ORDER BY export_id FOR UPDATE SKIP LOCKED LIMIT %s"
                    ") UPDATE governed_exports AS exports SET purged_at_utc=%s "
                    "FROM candidates WHERE exports.export_id=candidates.export_id "
                    f"RETURNING {_COLUMNS}",
                    (cutoff_utc, bounded, cutoff_utc),
                )
                rows = cursor.fetchall()
        return tuple(self._decode(row) for row in rows)

    def mark_purged(self, export_id: str, at_utc: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE governed_exports SET purged_at_utc=%s "
                    "WHERE export_id=%s AND purged_at_utc IS NULL",
                    (at_utc, export_id),
                )

    @staticmethod
    def _decode(row: Any) -> GovernedExport:
        values = list(row)
        for index in (9, 10, 11, 12):
            value = values[index]
            values[index] = "" if value is None else (
                value.isoformat() if hasattr(value, "isoformat") else str(value)
            )
        return GovernedExport(*values)
