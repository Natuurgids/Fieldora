"""Local-first records for marine science and maritime field operations."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


MARINE_RECORD_TYPES = (
    "sampling_station",
    "survey",
    "sample",
    "measurement",
    "species_observation",
    "edna_sample",
    "habitat",
    "acoustic_sonar",
)

MARITIME_RECORD_TYPES = (
    "vessel",
    "voyage",
    "port",
    "route",
    "crew",
    "equipment",
    "dive",
    "submarine_log",
    "operation_log",
)


@dataclass(frozen=True, slots=True)
class MarineMaritimeRecord:
    record_id: str
    domain: str
    record_type: str
    name: str
    status: str
    owner: str
    start_at: str
    end_at: str
    latitude: float | None
    longitude: float | None
    depth_m: float | None
    buddy: str
    notes: str
    metadata: dict[str, object]
    created_at_us: int
    updated_at_us: int


class MarineMaritimeService:
    """CRUD, attachments and immutable audit history in a dedicated database."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._ensure()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _ensure(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS marine_maritime_records(
                    record_id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL CHECK(domain IN ('marine','maritime')),
                    record_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner TEXT NOT NULL DEFAULT '',
                    start_at TEXT NOT NULL DEFAULT '',
                    end_at TEXT NOT NULL DEFAULT '',
                    latitude REAL,
                    longitude REAL,
                    depth_m REAL,
                    buddy TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_us INTEGER NOT NULL,
                    updated_at_us INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_marine_maritime_domain_type
                    ON marine_maritime_records(domain,record_type,updated_at_us DESC);
                CREATE TABLE IF NOT EXISTS marine_maritime_attachments(
                    attachment_id TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL REFERENCES marine_maritime_records(record_id)
                        ON DELETE CASCADE,
                    asset_id TEXT NOT NULL,
                    label TEXT NOT NULL DEFAULT '',
                    created_at_us INTEGER NOT NULL,
                    UNIQUE(record_id,asset_id)
                );
                CREATE TABLE IF NOT EXISTS marine_maritime_audit(
                    event_id TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at_us INTEGER NOT NULL
                );
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(marine_maritime_records)"
                )
            }
            if "depth_m" not in columns:
                connection.execute(
                    "ALTER TABLE marine_maritime_records ADD COLUMN depth_m REAL"
                )
            if "buddy" not in columns:
                connection.execute(
                    "ALTER TABLE marine_maritime_records "
                    "ADD COLUMN buddy TEXT NOT NULL DEFAULT ''"
                )

    @staticmethod
    def _validate(domain: str, record_type: str) -> None:
        allowed = MARINE_RECORD_TYPES if domain == "marine" else MARITIME_RECORD_TYPES
        if domain not in {"marine", "maritime"} or record_type not in allowed:
            raise ValueError(f"unsupported {domain} record type: {record_type}")

    def create(
        self,
        *,
        domain: str,
        record_type: str,
        name: str,
        status: str = "planned",
        owner: str = "",
        start_at: str = "",
        end_at: str = "",
        latitude: float | None = None,
        longitude: float | None = None,
        depth_m: float | None = None,
        buddy: str = "",
        notes: str = "",
        metadata: dict[str, object] | None = None,
        actor: str = "local-user",
    ) -> MarineMaritimeRecord:
        self._validate(domain, record_type)
        if not name.strip():
            raise ValueError("name is required")
        record_id = str(uuid4())
        now = time.time_ns() // 1000
        payload = metadata or {}
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO marine_maritime_records(
                    record_id,domain,record_type,name,status,owner,start_at,end_at,
                    latitude,longitude,depth_m,buddy,notes,metadata_json,
                    created_at_us,updated_at_us
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record_id, domain, record_type, name.strip(), status.strip() or "planned",
                    owner.strip(), start_at.strip(), end_at.strip(), latitude, longitude,
                    depth_m, buddy.strip(), notes.strip(),
                    json.dumps(payload, sort_keys=True), now, now,
                ),
            )
            self._audit(connection, record_id, "created", actor, {"record_type": record_type})
        return self.get(record_id)

    def list(self, domain: str, record_type: str | None = None) -> tuple[MarineMaritimeRecord, ...]:
        if domain not in {"marine", "maritime"}:
            raise ValueError(domain)
        sql = "SELECT * FROM marine_maritime_records WHERE domain=?"
        parameters: list[object] = [domain]
        if record_type:
            self._validate(domain, record_type)
            sql += " AND record_type=?"
            parameters.append(record_type)
        sql += " ORDER BY updated_at_us DESC,name COLLATE NOCASE"
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return tuple(self._row(row) for row in rows)

    def get(self, record_id: str) -> MarineMaritimeRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM marine_maritime_records WHERE record_id=?", (record_id,)
            ).fetchone()
        if row is None:
            raise KeyError(record_id)
        return self._row(row)

    def delete(self, record_id: str, *, actor: str = "local-user") -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT name,record_type FROM marine_maritime_records WHERE record_id=?",
                (record_id,),
            ).fetchone()
            if row is None:
                raise KeyError(record_id)
            self._audit(
                connection, record_id, "deleted", actor,
                {"name": str(row["name"]), "record_type": str(row["record_type"])},
            )
            connection.execute(
                "DELETE FROM marine_maritime_records WHERE record_id=?", (record_id,)
            )

    def attach_assets(
        self, record_id: str, asset_ids: tuple[str, ...], *, actor: str = "local-user"
    ) -> int:
        now = time.time_ns() // 1000
        with self._connect() as connection:
            if connection.execute(
                "SELECT 1 FROM marine_maritime_records WHERE record_id=?", (record_id,)
            ).fetchone() is None:
                raise KeyError(record_id)
            before = connection.total_changes
            connection.executemany(
                """
                INSERT OR IGNORE INTO marine_maritime_attachments(
                    attachment_id,record_id,asset_id,label,created_at_us
                ) VALUES(?,?,?,?,?)
                """,
                [(str(uuid4()), record_id, asset_id, "", now) for asset_id in asset_ids],
            )
            added = connection.total_changes - before
            if added:
                self._audit(connection, record_id, "assets-attached", actor, {"count": added})
        return added

    def attachment_ids(self, record_id: str) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT asset_id FROM marine_maritime_attachments "
                "WHERE record_id=? ORDER BY created_at_us",
                (record_id,),
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def export_records(self, domain: str) -> dict[str, object]:
        records = self.list(domain)
        return {
            "contract": "fieldora.marine-maritime.v1",
            "domain": domain,
            "exported_at_us": time.time_ns() // 1000,
            "records": [
                {
                    "record_id": item.record_id,
                    "record_type": item.record_type,
                    "name": item.name,
                    "status": item.status,
                    "owner": item.owner,
                    "start_at": item.start_at,
                    "end_at": item.end_at,
                    "latitude": item.latitude,
                    "longitude": item.longitude,
                    "depth_m": item.depth_m,
                    "buddy": item.buddy,
                    "notes": item.notes,
                    "metadata": item.metadata,
                    "asset_ids": list(self.attachment_ids(item.record_id)),
                }
                for item in records
            ],
        }

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        record_id: str,
        action: str,
        actor: str,
        payload: dict[str, object],
    ) -> None:
        connection.execute(
            "INSERT INTO marine_maritime_audit VALUES(?,?,?,?,?,?)",
            (
                str(uuid4()), record_id, action, actor,
                json.dumps(payload, sort_keys=True), time.time_ns() // 1000,
            ),
        )

    @staticmethod
    def _row(row: sqlite3.Row) -> MarineMaritimeRecord:
        return MarineMaritimeRecord(
            record_id=str(row["record_id"]),
            domain=str(row["domain"]),
            record_type=str(row["record_type"]),
            name=str(row["name"]),
            status=str(row["status"]),
            owner=str(row["owner"]),
            start_at=str(row["start_at"]),
            end_at=str(row["end_at"]),
            latitude=None if row["latitude"] is None else float(row["latitude"]),
            longitude=None if row["longitude"] is None else float(row["longitude"]),
            depth_m=None if row["depth_m"] is None else float(row["depth_m"]),
            buddy=str(row["buddy"]),
            notes=str(row["notes"]),
            metadata=json.loads(str(row["metadata_json"])),
            created_at_us=int(row["created_at_us"]),
            updated_at_us=int(row["updated_at_us"]),
        )
