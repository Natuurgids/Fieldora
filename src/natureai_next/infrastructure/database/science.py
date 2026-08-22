"""Incremental SQLite repository for Fieldora Science records."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

from natureai_next.domain.science import ScienceRevision, ScienceRevisionConflict
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


_COLLECTIONS = (
    "projects",
    "board",
    "activities",
    "artifacts",
    "dossiers",
    "project_stages",
    "project_activities",
    "project_resources",
    "project_budgets",
    "board_shapes",
    "whiteboards",
    "whiteboard_elements",
    "dossier_whiteboards",
    "dossier_links",
)


class SqliteScienceRepository:
    """Persist independent records and reject stale database snapshots."""

    def __init__(
        self, database_path: Path, default_snapshot: Callable[[], dict]
    ) -> None:
        self._factory = SqliteConnectionFactory(database_path)
        self._default_snapshot = default_snapshot
        self._ensure_schema()

    @property
    def database_path(self) -> Path:
        return self._factory.database_path

    def _ensure_schema(self) -> None:
        connection = self._factory.connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS science_state(
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    revision INTEGER NOT NULL CHECK(revision >= 0)
                );
                INSERT OR IGNORE INTO science_state(id,revision) VALUES(1,0);
                CREATE TABLE IF NOT EXISTS science_records(
                    collection_name TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    record_revision INTEGER NOT NULL CHECK(record_revision >= 1),
                    updated_at_us INTEGER NOT NULL,
                    PRIMARY KEY(collection_name,record_id)
                );
                CREATE INDEX IF NOT EXISTS ix_science_records_collection
                    ON science_records(collection_name,updated_at_us,record_id);
                """
            )
        finally:
            connection.close()

    @staticmethod
    def _record_id(collection: str, record: dict) -> str:
        if record.get("id"):
            return str(record["id"])
        if collection == "project_budgets":
            return str(record["project_id"])
        if collection == "dossier_whiteboards":
            return f"{record['dossier_id']}|{record['board_id']}"
        if collection == "dossier_links":
            return str(record.get("id") or f"{record['parent_dossier_id']}|{record['child_dossier_id']}")
        raise ValueError(f"Science {collection} record has no stable identity")

    @staticmethod
    def _encode(record: dict) -> str:
        return json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    def load_snapshot(self) -> tuple[dict, ScienceRevision]:
        snapshot = deepcopy(self._default_snapshot())
        connection = self._factory.connect(read_only=True)
        try:
            revision = ScienceRevision(
                int(
                    connection.execute(
                        "SELECT revision FROM science_state WHERE id=1"
                    ).fetchone()[0]
                )
            )
            rows = connection.execute(
                "SELECT collection_name,payload_json FROM science_records "
                "ORDER BY collection_name,updated_at_us,record_id"
            ).fetchall()
        finally:
            connection.close()
        for row in rows:
            collection = str(row["collection_name"])
            if collection in snapshot and isinstance(snapshot[collection], list):
                snapshot[collection].append(json.loads(str(row["payload_json"])))
        return snapshot, revision

    def save_snapshot(
        self, snapshot: dict, *, expected_revision: ScienceRevision
    ) -> ScienceRevision:
        desired: dict[tuple[str, str], str] = {}
        for collection in _COLLECTIONS:
            for record in snapshot.get(collection, []):
                record_id = self._record_id(collection, record)
                desired[(collection, record_id)] = self._encode(record)

        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = int(
                connection.execute(
                    "SELECT revision FROM science_state WHERE id=1"
                ).fetchone()[0]
            )
            if current != expected_revision.database_revision:
                raise ScienceRevisionConflict(
                    "Science data changed in another process. Reload before saving."
                )
            existing_rows = connection.execute(
                "SELECT collection_name,record_id,payload_json,record_revision "
                "FROM science_records"
            ).fetchall()
            existing = {
                (str(row["collection_name"]), str(row["record_id"])): (
                    str(row["payload_json"]), int(row["record_revision"])
                )
                for row in existing_rows
            }
            for key in existing.keys() - desired.keys():
                connection.execute(
                    "DELETE FROM science_records "
                    "WHERE collection_name=? AND record_id=?",
                    key,
                )
            changed = False
            for (collection, record_id), payload in desired.items():
                old = existing.get((collection, record_id))
                if old is not None and old[0] == payload:
                    continue
                changed = True
                record_revision = 1 if old is None else old[1] + 1
                connection.execute(
                    """
                    INSERT INTO science_records(
                        collection_name,record_id,payload_json,record_revision,updated_at_us
                    ) VALUES(?,?,?,?,CAST((julianday('now')-2440587.5)*86400000000 AS INTEGER))
                    ON CONFLICT(collection_name,record_id) DO UPDATE SET
                        payload_json=excluded.payload_json,
                        record_revision=excluded.record_revision,
                        updated_at_us=excluded.updated_at_us
                    """,
                    (collection, record_id, payload, record_revision),
                )
            if existing.keys() - desired.keys():
                changed = True
            next_revision = current + 1 if changed else current
            if changed:
                connection.execute(
                    "UPDATE science_state SET revision=? WHERE id=1",
                    (next_revision,),
                )
            connection.commit()
            return ScienceRevision(next_revision)
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_revision(self, collection: str, record_id: str) -> int:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT record_revision FROM science_records "
                "WHERE collection_name=? AND record_id=?",
                (collection, record_id),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError((collection, record_id))
        return int(row[0])
