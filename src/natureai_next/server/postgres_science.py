"""PostgreSQL repository for shared Fieldora Science records."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from natureai_next.application.science import default_science_snapshot
from natureai_next.domain.science import ScienceRevision, ScienceRevisionConflict
from natureai_next.server.postgres_operations_assets import PostgresOperationsSchema


class PostgresScienceRepository:
    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                # API and worker processes can start together on a clean database.
                # PostgreSQL's CREATE TABLE IF NOT EXISTS is not enough to protect
                # concurrent catalog/type creation, so serialize this schema bootstrap
                # transaction with a stable advisory lock.
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("fieldora_science_schema_v1",),
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS science_state(
                        singleton BOOLEAN PRIMARY KEY DEFAULT TRUE
                            CHECK(singleton),
                        revision BIGINT NOT NULL CHECK(revision >= 0)
                    )
                    """
                )
                cursor.execute(
                    "INSERT INTO science_state(singleton,revision) VALUES(TRUE,0) "
                    "ON CONFLICT(singleton) DO NOTHING"
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS science_records(
                        collection_name TEXT NOT NULL,
                        record_id TEXT NOT NULL,
                        payload_json JSONB NOT NULL,
                        record_revision BIGINT NOT NULL
                            CHECK(record_revision >= 1),
                        updated_at_us BIGINT NOT NULL,
                        PRIMARY KEY(collection_name,record_id)
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_science_records_collection_pg "
                    "ON science_records(collection_name,updated_at_us,record_id)"
                )
                for statement in PostgresOperationsSchema.statements():
                    cursor.execute(statement)

    _OPERATION_TABLES = {
        "ops_equipment_assets": ("ops_equipment_assets", ("id", "asset_code", "name", "category", "created_by", "created_at_us", "updated_at_us")),
        "ops_locations": ("ops_locations", ("id", "location_type", "code", "name", "created_at_us", "updated_at_us")),
        "ops_storage_conditions": ("ops_storage_conditions", ("id", "name", "created_at_us", "updated_at_us")),
        "ops_building_drawings": ("ops_building_drawings", ("id", "title", "source_format", "file_path", "created_by", "created_at_us", "updated_at_us")),
        "ops_drawing_markers": ("ops_drawing_markers", ("id", "drawing_id", "marker_code", "x", "y", "created_at_us", "updated_at_us")),
        "ops_asset_documents": ("ops_asset_documents", ("id", "asset_id", "document_type", "title", "file_path", "created_by", "created_at_us")),
        "ops_asset_movements": ("ops_asset_movements", ("id", "asset_id", "moved_at", "moved_by", "created_at_us", "updated_at_us")),
        "ops_maintenance_events": ("ops_maintenance_events", ("id", "asset_id", "maintenance_type", "status", "created_by", "created_at_us", "updated_at_us")),
        "ops_calibration_events": ("ops_calibration_events", ("id", "asset_id", "status", "created_by", "created_at_us", "updated_at_us")),
    }

    def _validate_operation_record(self, collection: str, record: dict) -> None:
        spec = self._OPERATION_TABLES.get(collection)
        if spec is None:
            return
        missing = [name for name in spec[1] if record.get(name) in (None, "")]
        if missing:
            raise ValueError("missing required Operations fields: " + ", ".join(missing))

    def _write_operation_record(self, cursor, collection: str, record: dict) -> None:
        spec = self._OPERATION_TABLES.get(collection)
        if spec is None:
            return
        from psycopg import sql

        table = spec[0]
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position",
            (table,),
        )
        allowed = {str(row[0]) for row in cursor.fetchall()}
        values = {key: value for key, value in record.items() if key in allowed}
        columns = tuple(values)
        if not columns or "id" not in values:
            raise ValueError("Operations record has no writable stable identity")
        assignments = sql.SQL(",").join(
            sql.SQL("{}=EXCLUDED.{}").format(sql.Identifier(name), sql.Identifier(name))
            for name in columns
            if name != "id"
        )
        query = sql.SQL(
            "INSERT INTO {}({}) VALUES({}) ON CONFLICT(id) DO UPDATE SET {}"
        ).format(
            sql.Identifier(table),
            sql.SQL(",").join(sql.Identifier(name) for name in columns),
            sql.SQL(",").join(sql.Placeholder() for _ in columns),
            assignments,
        )
        cursor.execute(query, tuple(values[name] for name in columns))

    def records(self, collection: str) -> tuple[dict, ...]:
        if collection in self._OPERATION_TABLES:
            from psycopg import sql

            table = self._OPERATION_TABLES[collection][0]
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        sql.SQL("SELECT * FROM {} ORDER BY created_at_us,id").format(
                            sql.Identifier(table)
                        )
                    )
                    names = tuple(item[0] for item in cursor.description)
                    rows = cursor.fetchall()
            return tuple(
                {
                    name: (str(value) if hasattr(value, "hex") else value)
                    for name, value in zip(names, row)
                }
                for row in rows
            )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT payload_json FROM science_records "
                    "WHERE collection_name=%s ORDER BY updated_at_us,record_id",
                    (collection,),
                )
                rows = cursor.fetchall()
        return tuple(self._payload(row[0]) for row in rows)

    def put(
        self, collection: str, record: dict, expected_revision: int | None
    ) -> int:
        record_id = str(record["id"])
        self._validate_operation_record(collection, record)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._write_operation_record(cursor, collection, record)
                cursor.execute(
                    "SELECT record_revision FROM science_records "
                    "WHERE collection_name=%s AND record_id=%s FOR UPDATE",
                    (collection, record_id),
                )
                row = cursor.fetchone()
                current = 0 if row is None else int(row[0])
                if expected_revision is not None and current != expected_revision:
                    raise ValueError("revision_conflict")
                revision = current + 1
                cursor.execute(
                    "INSERT INTO science_records("
                    "collection_name,record_id,payload_json,record_revision,updated_at_us"
                    ") VALUES(%s,%s,%s::jsonb,%s,%s) "
                    "ON CONFLICT(collection_name,record_id) DO UPDATE SET "
                    "payload_json=excluded.payload_json,"
                    "record_revision=excluded.record_revision,"
                    "updated_at_us=excluded.updated_at_us",
                    (
                        collection,
                        record_id,
                        self._encode(record),
                        revision,
                        time.time_ns() // 1000,
                    ),
                )
                cursor.execute(
                    "UPDATE science_state SET revision=revision+1 "
                    "WHERE singleton=TRUE"
                )
        return revision

    def load_snapshot(self) -> tuple[dict, ScienceRevision]:
        snapshot = deepcopy(default_science_snapshot())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT revision FROM science_state WHERE singleton=TRUE"
                )
                revision = ScienceRevision(int(cursor.fetchone()[0]))
                cursor.execute(
                    "SELECT collection_name,payload_json FROM science_records "
                    "ORDER BY collection_name,updated_at_us,record_id"
                )
                rows = cursor.fetchall()
        for collection, payload in rows:
            name = str(collection)
            if name in snapshot and isinstance(snapshot[name], list):
                snapshot[name].append(self._payload(payload))
        return snapshot, revision

    def save_snapshot(
        self, snapshot: dict, *, expected_revision: ScienceRevision
    ) -> ScienceRevision:
        desired: dict[tuple[str, str], str] = {}
        for collection, values in snapshot.items():
            if collection == "schema_version" or not isinstance(values, list):
                continue
            for record in values:
                record_id = self._record_id(collection, record)
                desired[(collection, record_id)] = self._encode(record)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT revision FROM science_state "
                    "WHERE singleton=TRUE FOR UPDATE"
                )
                current = int(cursor.fetchone()[0])
                if current != expected_revision.database_revision:
                    raise ScienceRevisionConflict(
                        "Science data changed in another process. Reload before saving."
                    )
                cursor.execute(
                    "SELECT collection_name,record_id,payload_json,record_revision "
                    "FROM science_records"
                )
                existing = {
                    (str(row[0]), str(row[1])): (
                        self._encode(self._payload(row[2])),
                        int(row[3]),
                    )
                    for row in cursor.fetchall()
                }
                removed = existing.keys() - desired.keys()
                for collection, record_id in removed:
                    cursor.execute(
                        "DELETE FROM science_records "
                        "WHERE collection_name=%s AND record_id=%s",
                        (collection, record_id),
                    )
                changed = bool(removed)
                for (collection, record_id), payload in desired.items():
                    old = existing.get((collection, record_id))
                    if old is not None and old[0] == payload:
                        continue
                    changed = True
                    record_revision = 1 if old is None else old[1] + 1
                    cursor.execute(
                        "INSERT INTO science_records("
                        "collection_name,record_id,payload_json,record_revision,"
                        "updated_at_us) VALUES(%s,%s,%s::jsonb,%s,%s) "
                        "ON CONFLICT(collection_name,record_id) DO UPDATE SET "
                        "payload_json=excluded.payload_json,"
                        "record_revision=excluded.record_revision,"
                        "updated_at_us=excluded.updated_at_us",
                        (
                            collection,
                            record_id,
                            payload,
                            record_revision,
                            time.time_ns() // 1000,
                        ),
                    )
                next_revision = current + 1 if changed else current
                if changed:
                    cursor.execute(
                        "UPDATE science_state SET revision=%s "
                        "WHERE singleton=TRUE",
                        (next_revision,),
                    )
        return ScienceRevision(next_revision)

    @staticmethod
    def _record_id(collection: str, record: dict) -> str:
        if record.get("id"):
            return str(record["id"])
        if collection == "project_budgets":
            return str(record["project_id"])
        if collection == "dossier_whiteboards":
            return f"{record['dossier_id']}|{record['board_id']}"
        raise ValueError(f"Science {collection} record has no stable identity")

    @staticmethod
    def _encode(record: dict) -> str:
        return json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    @staticmethod
    def _payload(value: Any) -> dict:
        payload = json.loads(value) if isinstance(value, str) else value
        if not isinstance(payload, dict):
            raise ValueError("Science record payload must be an object")
        return payload
