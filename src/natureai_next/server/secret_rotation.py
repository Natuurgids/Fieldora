"""Metadata-only coordination for externally managed production secrets."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SecretVersion:
    purpose: str
    version_id: str
    provider_reference: str
    state: str
    activated_at_epoch: int | None
    retired_at_epoch: int | None


class SecretRotationRegistry:
    _REFERENCE_PREFIXES = ("vault://", "kms://", "external-secret://")

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._ensure()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _ensure(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS secret_versions(
                    purpose TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    provider_reference TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('staged','active','retired')),
                    created_at_epoch INTEGER NOT NULL,
                    activated_at_epoch INTEGER,
                    retired_at_epoch INTEGER,
                    PRIMARY KEY(purpose,version_id)
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_secret_active_purpose
                ON secret_versions(purpose) WHERE state='active'
                """
            )

    def stage(
        self,
        purpose: str,
        version_id: str,
        provider_reference: str,
        created_at_epoch: int,
    ) -> None:
        if not purpose.strip() or not version_id.strip():
            raise ValueError("purpose and version id are required")
        if not provider_reference.startswith(self._REFERENCE_PREFIXES):
            raise ValueError("only external provider references may be registered")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO secret_versions(
                    purpose,version_id,provider_reference,state,created_at_epoch
                ) VALUES(?,?,?,'staged',?)
                """,
                (purpose, version_id, provider_reference, created_at_epoch),
            )

    def activate(
        self,
        purpose: str,
        version_id: str,
        activated_at_epoch: int,
        *,
        expected_active_version: str | None,
    ) -> SecretVersion:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """
                SELECT version_id FROM secret_versions
                WHERE purpose=? AND state='active'
                """,
                (purpose,),
            ).fetchone()
            current_id = None if current is None else str(current["version_id"])
            if current_id != expected_active_version:
                connection.rollback()
                raise ValueError("active_version_conflict")
            staged = connection.execute(
                """
                SELECT 1 FROM secret_versions
                WHERE purpose=? AND version_id=? AND state='staged'
                """,
                (purpose, version_id),
            ).fetchone()
            if staged is None:
                connection.rollback()
                raise ValueError("secret version is not staged")
            if current_id is not None:
                connection.execute(
                    """
                    UPDATE secret_versions
                    SET state='retired',retired_at_epoch=?
                    WHERE purpose=? AND version_id=? AND state='active'
                    """,
                    (activated_at_epoch, purpose, current_id),
                )
            connection.execute(
                """
                UPDATE secret_versions
                SET state='active',activated_at_epoch=?
                WHERE purpose=? AND version_id=? AND state='staged'
                """,
                (activated_at_epoch, purpose, version_id),
            )
            connection.commit()
        result = self.active(purpose)
        if result is None:
            raise RuntimeError("secret activation did not persist")
        return result

    def active(self, purpose: str) -> SecretVersion | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT purpose,version_id,provider_reference,state,
                       activated_at_epoch,retired_at_epoch
                FROM secret_versions WHERE purpose=? AND state='active'
                """,
                (purpose,),
            ).fetchone()
        return None if row is None else SecretVersion(*row)

    def versions(self, purpose: str) -> tuple[SecretVersion, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT purpose,version_id,provider_reference,state,
                       activated_at_epoch,retired_at_epoch
                FROM secret_versions WHERE purpose=?
                ORDER BY created_at_epoch,version_id
                """,
                (purpose,),
            ).fetchall()
        return tuple(SecretVersion(*row) for row in rows)
