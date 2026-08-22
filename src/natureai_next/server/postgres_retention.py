"""PostgreSQL retention leases and legal holds for multi-server workers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from natureai_next.server.retention import RetentionCandidate


class PostgresRetentionStore:
    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS retained_resources(
                        organization_id TEXT NOT NULL,
                        resource_type TEXT NOT NULL,
                        resource_id TEXT NOT NULL,
                        expires_at_epoch BIGINT NOT NULL,
                        lease_owner TEXT,
                        lease_until_epoch BIGINT,
                        lease_token BIGINT NOT NULL DEFAULT 0,
                        removed_at_epoch BIGINT,
                        PRIMARY KEY(organization_id,resource_type,resource_id)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS ix_retained_resources_due_pg
                    ON retained_resources(removed_at_epoch,expires_at_epoch)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS legal_holds(
                        hold_id TEXT PRIMARY KEY,
                        organization_id TEXT NOT NULL,
                        resource_type TEXT,
                        resource_id TEXT,
                        reason TEXT NOT NULL,
                        active BOOLEAN NOT NULL,
                        created_at_epoch BIGINT NOT NULL,
                        released_at_epoch BIGINT
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS ix_legal_holds_scope_pg
                    ON legal_holds(organization_id,active,resource_type,resource_id)
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
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO retained_resources(
                        organization_id,resource_type,resource_id,expires_at_epoch
                    ) VALUES(%s,%s,%s,%s)
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
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO legal_holds(
                        hold_id,organization_id,resource_type,resource_id,
                        reason,active,created_at_epoch
                    ) VALUES(%s,%s,%s,%s,%s,TRUE,%s)
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
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE legal_holds SET active=FALSE,released_at_epoch=%s
                    WHERE hold_id=%s AND active=TRUE
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
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH candidates AS (
                        SELECT r.organization_id,r.resource_type,r.resource_id
                        FROM retained_resources r
                        WHERE r.removed_at_epoch IS NULL
                          AND r.expires_at_epoch<=%s
                          AND (
                            r.lease_until_epoch IS NULL OR r.lease_until_epoch<=%s
                          )
                          AND NOT EXISTS(
                            SELECT 1 FROM legal_holds h
                            WHERE h.organization_id=r.organization_id
                              AND h.active=TRUE
                              AND (
                                h.resource_type IS NULL
                                OR h.resource_type=r.resource_type
                              )
                              AND (
                                h.resource_id IS NULL
                                OR h.resource_id=r.resource_id
                              )
                          )
                        ORDER BY r.expires_at_epoch,r.resource_type,r.resource_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT %s
                    )
                    UPDATE retained_resources AS r
                    SET lease_owner=%s,lease_until_epoch=%s,
                        lease_token=r.lease_token+1
                    FROM candidates AS c
                    WHERE r.organization_id=c.organization_id
                      AND r.resource_type=c.resource_type
                      AND r.resource_id=c.resource_id
                    RETURNING r.organization_id,r.resource_type,r.resource_id,
                              r.expires_at_epoch,r.lease_token
                    """,
                    (now_epoch, now_epoch, bounded, worker_id, now_epoch + lease_seconds),
                )
                rows = cursor.fetchall()
        return tuple(RetentionCandidate(*row) for row in rows)

    def complete_removal(
        self,
        candidate: RetentionCandidate,
        worker_id: str,
        removed_at_epoch: int,
    ) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE retained_resources
                    SET removed_at_epoch=%s,lease_owner=NULL,lease_until_epoch=NULL
                    WHERE organization_id=%s AND resource_type=%s AND resource_id=%s
                      AND lease_owner=%s AND lease_token=%s
                      AND removed_at_epoch IS NULL
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
