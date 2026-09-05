"""Project/collection/submission associations for governed Library media.

The media object is owned by the organization Library. Associations describe how the
same evidence participates in projects, collections, dossiers, submissions, and other
contexts without copying the bytes or changing media identity.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class MediaAssociation:
    media_id: str
    organization_id: str
    association_type: str
    target_id: str
    purpose: str
    linked_by: str
    linked_at_epoch: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class MediaAssociationRepository(Protocol):
    def link(self, association: MediaAssociation) -> None: ...
    def unlink(
        self,
        media_id: str,
        organization_id: str,
        association_type: str,
        target_id: str,
    ) -> None: ...
    def links(
        self, media_id: str, organization_id: str
    ) -> tuple[MediaAssociation, ...]: ...
    def linked_media_ids(
        self, organization_id: str, association_type: str, target_id: str
    ) -> tuple[str, ...]: ...


class SqliteMediaAssociationRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS governed_media_associations(
                    media_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    association_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    linked_by TEXT NOT NULL,
                    linked_at_epoch INTEGER NOT NULL,
                    PRIMARY KEY(media_id,association_type,target_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_governed_media_associations_target "
                "ON governed_media_associations(organization_id,association_type,target_id)"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def link(self, association: MediaAssociation) -> None:
        _validate(association)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO governed_media_associations(
                    media_id,organization_id,association_type,target_id,purpose,
                    linked_by,linked_at_epoch
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(media_id,association_type,target_id) DO UPDATE SET
                    organization_id=excluded.organization_id,
                    purpose=excluded.purpose,
                    linked_by=excluded.linked_by,
                    linked_at_epoch=excluded.linked_at_epoch
                """,
                tuple(asdict(association).values()),
            )

    def unlink(
        self,
        media_id: str,
        organization_id: str,
        association_type: str,
        target_id: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM governed_media_associations WHERE media_id=? "
                "AND organization_id=? AND association_type=? AND target_id=?",
                (media_id, organization_id, association_type, target_id),
            )

    def links(
        self, media_id: str, organization_id: str
    ) -> tuple[MediaAssociation, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT media_id,organization_id,association_type,target_id,purpose,"
                "linked_by,linked_at_epoch FROM governed_media_associations "
                "WHERE media_id=? AND organization_id=? "
                "ORDER BY association_type,target_id",
                (media_id, organization_id),
            ).fetchall()
        return tuple(MediaAssociation(*row) for row in rows)

    def linked_media_ids(
        self, organization_id: str, association_type: str, target_id: str
    ) -> tuple[str, ...]:
        if association_type not in _ALLOWED_ASSOCIATION_TYPES:
            raise ValueError("unsupported media association type")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT media_id FROM governed_media_associations "
                "WHERE organization_id=? AND association_type=? AND target_id=? "
                "ORDER BY media_id",
                (organization_id, association_type, target_id),
            ).fetchall()
        return tuple(str(row[0]) for row in rows)


class PostgresMediaAssociationRepository:
    def __init__(self, connect: Callable[[], Any], *, initialize: bool = True) -> None:
        self._connect = connect
        if initialize:
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtext(%s))",
                        ("fieldora_media_schema_v1",),
                    )
                    self.bootstrap_schema(cursor)

    @staticmethod
    def bootstrap_schema(cursor: Any) -> None:
        """Create association schema inside the caller's serialized transaction."""
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS governed_media_associations(
                media_id TEXT NOT NULL,
                organization_id TEXT NOT NULL,
                association_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                purpose TEXT NOT NULL,
                linked_by TEXT NOT NULL,
                linked_at_epoch BIGINT NOT NULL,
                PRIMARY KEY(media_id,association_type,target_id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_governed_media_associations_target_pg "
            "ON governed_media_associations(organization_id,association_type,target_id)"
        )

    def link(self, association: MediaAssociation) -> None:
        _validate(association)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO governed_media_associations(
                        media_id,organization_id,association_type,target_id,purpose,
                        linked_by,linked_at_epoch
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(media_id,association_type,target_id) DO UPDATE SET
                        organization_id=EXCLUDED.organization_id,
                        purpose=EXCLUDED.purpose,
                        linked_by=EXCLUDED.linked_by,
                        linked_at_epoch=EXCLUDED.linked_at_epoch
                    """,
                    tuple(asdict(association).values()),
                )

    def unlink(
        self,
        media_id: str,
        organization_id: str,
        association_type: str,
        target_id: str,
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM governed_media_associations WHERE media_id=%s "
                    "AND organization_id=%s AND association_type=%s AND target_id=%s",
                    (media_id, organization_id, association_type, target_id),
                )

    def links(
        self, media_id: str, organization_id: str
    ) -> tuple[MediaAssociation, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT media_id,organization_id,association_type,target_id,purpose,"
                    "linked_by,linked_at_epoch FROM governed_media_associations "
                    "WHERE media_id=%s AND organization_id=%s "
                    "ORDER BY association_type,target_id",
                    (media_id, organization_id),
                )
                rows = cursor.fetchall()
        return tuple(MediaAssociation(*row) for row in rows)

    def linked_media_ids(
        self, organization_id: str, association_type: str, target_id: str
    ) -> tuple[str, ...]:
        if association_type not in _ALLOWED_ASSOCIATION_TYPES:
            raise ValueError("unsupported media association type")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT media_id FROM governed_media_associations "
                    "WHERE organization_id=%s AND association_type=%s AND target_id=%s "
                    "ORDER BY media_id",
                    (organization_id, association_type, target_id),
                )
                rows = cursor.fetchall()
        return tuple(str(row[0]) for row in rows)


def new_association(
    *,
    media_id: str,
    organization_id: str,
    association_type: str,
    target_id: str,
    purpose: str,
    linked_by: str,
    now_epoch: int | None = None,
) -> MediaAssociation:
    association = MediaAssociation(
        media_id.strip(),
        organization_id.strip(),
        association_type.strip(),
        target_id.strip(),
        purpose.strip() or "reference",
        linked_by.strip(),
        int(time.time()) if now_epoch is None else int(now_epoch),
    )
    _validate(association)
    return association


_ALLOWED_ASSOCIATION_TYPES = {
    "project",
    "collection",
    "dossier",
    "submission",
    "review_case",
}


def _validate(association: MediaAssociation) -> None:
    if association.association_type not in _ALLOWED_ASSOCIATION_TYPES:
        raise ValueError("unsupported media association type")
    if not all(
        (
            association.media_id,
            association.organization_id,
            association.target_id,
            association.linked_by,
        )
    ):
        raise ValueError("media association identity fields are required")
