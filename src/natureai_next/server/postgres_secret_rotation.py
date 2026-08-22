"""Shared PostgreSQL coordination for externally managed production secrets."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from natureai_next.server.secret_rotation import SecretVersion


class PostgresSecretRotationRegistry:
    _REFERENCE_PREFIXES = ("vault://", "kms://", "external-secret://")

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        self._ensure()

    def _ensure(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS secret_versions(
                        purpose TEXT NOT NULL,
                        version_id TEXT NOT NULL,
                        provider_reference TEXT NOT NULL,
                        state TEXT NOT NULL
                            CHECK(state IN ('staged','active','retired')),
                        created_at_epoch BIGINT NOT NULL,
                        activated_at_epoch BIGINT,
                        retired_at_epoch BIGINT,
                        PRIMARY KEY(purpose,version_id)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS ux_secret_active_purpose
                    ON secret_versions(purpose) WHERE state='active'
                    """
                )
            connection.commit()

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
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO secret_versions(
                        purpose,version_id,provider_reference,state,created_at_epoch
                    ) VALUES(%s,%s,%s,'staged',%s)
                    """,
                    (purpose, version_id, provider_reference, created_at_epoch),
                )
            connection.commit()

    def activate(
        self,
        purpose: str,
        version_id: str,
        activated_at_epoch: int,
        *,
        expected_active_version: str | None,
    ) -> SecretVersion:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("fieldora-secret:" + purpose,),
                )
                cursor.execute(
                    """
                    SELECT version_id FROM secret_versions
                    WHERE purpose=%s AND state='active'
                    FOR UPDATE
                    """,
                    (purpose,),
                )
                current = cursor.fetchone()
                current_id = None if current is None else str(current[0])
                if current_id != expected_active_version:
                    raise ValueError("active_version_conflict")
                cursor.execute(
                    """
                    SELECT 1 FROM secret_versions
                    WHERE purpose=%s AND version_id=%s AND state='staged'
                    FOR UPDATE
                    """,
                    (purpose, version_id),
                )
                if cursor.fetchone() is None:
                    raise ValueError("secret version is not staged")
                if current_id is not None:
                    cursor.execute(
                        """
                        UPDATE secret_versions
                        SET state='retired',retired_at_epoch=%s
                        WHERE purpose=%s AND version_id=%s AND state='active'
                        """,
                        (activated_at_epoch, purpose, current_id),
                    )
                cursor.execute(
                    """
                    UPDATE secret_versions
                    SET state='active',activated_at_epoch=%s
                    WHERE purpose=%s AND version_id=%s AND state='staged'
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
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT purpose,version_id,provider_reference,state,
                           activated_at_epoch,retired_at_epoch
                    FROM secret_versions WHERE purpose=%s AND state='active'
                    """,
                    (purpose,),
                )
                row = cursor.fetchone()
        return None if row is None else SecretVersion(*row)

    def versions(self, purpose: str) -> tuple[SecretVersion, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT purpose,version_id,provider_reference,state,
                           activated_at_epoch,retired_at_epoch
                    FROM secret_versions WHERE purpose=%s
                    ORDER BY created_at_epoch,version_id
                    """,
                    (purpose,),
                )
                rows = cursor.fetchall()
        return tuple(SecretVersion(*row) for row in rows)
