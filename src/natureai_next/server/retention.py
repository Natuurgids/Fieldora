"""Retention scheduling with durable leases and legal-hold exclusion."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RetentionCandidate:
    organization_id: str
    resource_type: str
    resource_id: str
    expires_at_epoch: int
    lease_token: int


class RetentionStore:
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
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS retained_resources(
                    organization_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    expires_at_epoch INTEGER NOT NULL,
                    lease_owner TEXT,
                    lease_until_epoch INTEGER,
                    lease_token INTEGER NOT NULL DEFAULT 0,
                    removed_at_epoch INTEGER,
                    PRIMARY KEY(organization_id,resource_type,resource_id)
                );
                CREATE INDEX IF NOT EXISTS idx_retained_resources_due
                    ON retained_resources(removed_at_epoch,expires_at_epoch);
                CREATE TABLE IF NOT EXISTS legal_holds(
                    hold_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    resource_type TEXT,
                    resource_id TEXT,
                    reason TEXT NOT NULL,
                    active INTEGER NOT NULL CHECK(active IN (0,1)),
                    created_at_epoch INTEGER NOT NULL,
                    released_at_epoch INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_legal_holds_scope
                    ON legal_holds(organization_id,active,resource_type,resource_id);
                """
            )

    def register(
        self,
        organization_id: str,
        resource_type: str,
        resource_id: str,
        expires_at_epoch: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO retained_resources(
                    organization_id,resource_type,resource_id,expires_at_epoch
                ) VALUES(?,?,?,?)
                ON CONFLICT(organization_id,resource_type,resource_id)
                DO UPDATE SET expires_at_epoch=excluded.expires_at_epoch
                WHERE retained_resources.removed_at_epoch IS NULL
                """,
                (organization_id, resource_type, resource_id, expires_at_epoch),
            )

    def place_hold(
        self,
        hold_id: str,
        organization_id: str,
        reason: str,
        created_at_epoch: int,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        if resource_id is not None and resource_type is None:
            raise ValueError("resource-specific holds require a resource type")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO legal_holds(
                    hold_id,organization_id,resource_type,resource_id,
                    reason,active,created_at_epoch
                ) VALUES(?,?,?,?,?,1,?)
                """,
                (
                    hold_id,
                    organization_id,
                    resource_type,
                    resource_id,
                    reason,
                    created_at_epoch,
                ),
            )

    def release_hold(self, hold_id: str, released_at_epoch: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE legal_holds SET active=0,released_at_epoch=?
                WHERE hold_id=? AND active=1
                """,
                (released_at_epoch, hold_id),
            )
            return cursor.rowcount == 1

    def claim_due(
        self,
        worker_id: str,
        now_epoch: int,
        *,
        lease_seconds: int = 300,
        limit: int = 100,
    ) -> tuple[RetentionCandidate, ...]:
        if not worker_id.strip() or len(worker_id) > 200:
            raise ValueError("worker_id must contain 1 to 200 characters")
        if not 1 <= lease_seconds <= 86_400:
            raise ValueError("lease_seconds must be between 1 and 86400")
        bounded = max(1, min(limit, 1000))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT r.organization_id,r.resource_type,r.resource_id,
                       r.expires_at_epoch,r.lease_token
                FROM retained_resources r
                WHERE r.removed_at_epoch IS NULL
                  AND r.expires_at_epoch<=?
                  AND (r.lease_until_epoch IS NULL OR r.lease_until_epoch<=?)
                  AND NOT EXISTS(
                    SELECT 1 FROM legal_holds h
                    WHERE h.organization_id=r.organization_id AND h.active=1
                      AND (h.resource_type IS NULL OR h.resource_type=r.resource_type)
                      AND (h.resource_id IS NULL OR h.resource_id=r.resource_id)
                  )
                ORDER BY r.expires_at_epoch,r.resource_type,r.resource_id
                LIMIT ?
                """,
                (now_epoch, now_epoch, bounded),
            ).fetchall()
            claimed = []
            for row in rows:
                token = int(row["lease_token"]) + 1
                connection.execute(
                    """
                    UPDATE retained_resources
                    SET lease_owner=?,lease_until_epoch=?,lease_token=?
                    WHERE organization_id=? AND resource_type=? AND resource_id=?
                    """,
                    (
                        worker_id,
                        now_epoch + lease_seconds,
                        token,
                        row["organization_id"],
                        row["resource_type"],
                        row["resource_id"],
                    ),
                )
                claimed.append(
                    RetentionCandidate(
                        str(row["organization_id"]),
                        str(row["resource_type"]),
                        str(row["resource_id"]),
                        int(row["expires_at_epoch"]),
                        token,
                    )
                )
            connection.commit()
        return tuple(claimed)

    def complete_removal(
        self,
        candidate: RetentionCandidate,
        worker_id: str,
        removed_at_epoch: int,
    ) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE retained_resources
                SET removed_at_epoch=?,lease_owner=NULL,lease_until_epoch=NULL
                WHERE organization_id=? AND resource_type=? AND resource_id=?
                  AND lease_owner=? AND lease_token=? AND removed_at_epoch IS NULL
                """,
                (
                    removed_at_epoch,
                    candidate.organization_id,
                    candidate.resource_type,
                    candidate.resource_id,
                    worker_id,
                    candidate.lease_token,
                ),
            )
            return cursor.rowcount == 1
