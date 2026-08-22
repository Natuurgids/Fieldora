"""Aperture-owned source registry and recoverable lifecycle operations."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


class SourceState(StrEnum):
    INSTALLED = "installed"
    OFFLINE = "offline"
    REMOVED = "removed"
    MISSING = "missing"
    SUPERSEDED = "superseded"
    INACTIVE = "inactive"
    REQUIRES_DOWNLOAD = "requires_download"
    UPDATE_AVAILABLE = "update_available"


@dataclass(frozen=True, slots=True)
class SourceRecord:
    source_id: str
    kind: str
    display_name: str
    version: str
    state: SourceState
    licence: str | None = None
    attribution: str | None = None
    checksum: str | None = None


@dataclass(frozen=True, slots=True)
class SourceInstallation:
    source_id: str
    runtime_path: Path | None = None
    index_path: Path | None = None
    replacement_source_id: str | None = None
    last_verified_at_us: int | None = None
    last_error: str | None = None


@dataclass(frozen=True, slots=True)
class SourceRemovalOptions:
    remove_runtime_files: bool = True
    remove_indexes_and_caches: bool = True
    delete_pending_results: bool = False
    delete_rejected_results: bool = True
    delete_accepted_enrichment: bool = False


class SourceRegistryService:
    def __init__(self, database_path: Path) -> None:
        self._factory = SqliteConnectionFactory(database_path)

    @staticmethod
    def _now() -> int:
        return time.time_ns() // 1000

    def _event(
        self, connection, source_id: str, action: str, from_state, to_state, details=None
    ) -> None:
        connection.execute(
            "INSERT INTO source_lifecycle_events(source_id,action,from_state,to_state,details_json,created_at_us) VALUES(?,?,?,?,?,?)",
            (
                source_id,
                action,
                from_state,
                to_state,
                json.dumps(details or {}, sort_keys=True),
                self._now(),
            ),
        )

    def register(self, record: SourceRecord) -> None:
        now = self._now()
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                "SELECT state,version FROM source_records WHERE source_id=?", (record.source_id,)
            ).fetchone()
            connection.execute(
                """INSERT INTO source_records(source_id,kind,display_name,version,state,licence,attribution,checksum,created_at_us,updated_at_us)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET kind=excluded.kind,display_name=excluded.display_name,
                version=excluded.version,state=excluded.state,licence=excluded.licence,attribution=excluded.attribution,
                checksum=excluded.checksum,updated_at_us=excluded.updated_at_us""",
                (
                    record.source_id,
                    record.kind,
                    record.display_name,
                    record.version,
                    record.state.value,
                    record.licence,
                    record.attribution,
                    record.checksum,
                    now,
                    now,
                ),
            )
            self._event(
                connection,
                record.source_id,
                "register",
                None if previous is None else previous[0],
                record.state.value,
                {
                    "version": record.version,
                    "previous_version": None if previous is None else previous[1],
                },
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def set_state(self, source_id: str, state: SourceState, *, reason: str | None = None) -> None:
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM source_records WHERE source_id=?", (source_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown source: {source_id}")
            connection.execute(
                "UPDATE source_records SET state=?,updated_at_us=? WHERE source_id=?",
                (state.value, self._now(), source_id),
            )
            self._event(
                connection,
                source_id,
                "state_change",
                row[0],
                state.value,
                {"reason": reason} if reason else {},
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def attach_installation(
        self, source_id: str, *, runtime_path: Path | None = None, index_path: Path | None = None
    ) -> None:
        connection = self._factory.connect()
        try:
            if (
                connection.execute(
                    "SELECT 1 FROM source_records WHERE source_id=?", (source_id,)
                ).fetchone()
                is None
            ):
                raise KeyError(f"unknown source: {source_id}")
            connection.execute(
                """INSERT INTO source_installations(source_id,runtime_path,index_path) VALUES(?,?,?)
                ON CONFLICT(source_id) DO UPDATE SET runtime_path=excluded.runtime_path,index_path=excluded.index_path""",
                (
                    source_id,
                    None if runtime_path is None else str(runtime_path),
                    None if index_path is None else str(index_path),
                ),
            )
        finally:
            connection.close()

    def installation(self, source_id: str) -> SourceInstallation:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT source_id,runtime_path,index_path,replacement_source_id,last_verified_at_us,last_error FROM source_installations WHERE source_id=?",
                (source_id,),
            ).fetchone()
            if row is None:
                return SourceInstallation(source_id)
            return SourceInstallation(
                str(row[0]),
                Path(row[1]) if row[1] else None,
                Path(row[2]) if row[2] else None,
                row[3],
                row[4],
                row[5],
            )
        finally:
            connection.close()

    def verify_installation(self, source_id: str) -> SourceState:
        record = self.get(source_id)
        installation = self.installation(source_id)
        expected = tuple(
            path
            for path in (installation.runtime_path, installation.index_path)
            if path is not None
        )
        missing = [str(path) for path in expected if not path.exists()]
        next_state = (
            SourceState.MISSING
            if missing
            else (
                SourceState.INSTALLED
                if record.state
                in {SourceState.MISSING, SourceState.REMOVED, SourceState.REQUIRES_DOWNLOAD}
                else record.state
            )
        )
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE source_records SET state=?,updated_at_us=? WHERE source_id=?",
                (next_state.value, self._now(), source_id),
            )
            connection.execute(
                """INSERT INTO source_installations(source_id,last_verified_at_us,last_error) VALUES(?,?,?)
                ON CONFLICT(source_id) DO UPDATE SET last_verified_at_us=excluded.last_verified_at_us,last_error=excluded.last_error""",
                (source_id, self._now(), None if not missing else "Missing: " + ", ".join(missing)),
            )
            self._event(
                connection,
                source_id,
                "verify",
                record.state.value,
                next_state.value,
                {"missing": missing},
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return next_state

    def recover(
        self, source_id: str, *, runtime_path: Path | None = None, index_path: Path | None = None
    ) -> SourceState:
        if runtime_path is not None or index_path is not None:
            current = self.installation(source_id)
            self.attach_installation(
                source_id,
                runtime_path=runtime_path or current.runtime_path,
                index_path=index_path or current.index_path,
            )
        state = self.verify_installation(source_id)
        if state is SourceState.MISSING:
            raise FileNotFoundError(
                self.installation(source_id).last_error or "source files are missing"
            )
        return state

    def supersede(
        self,
        source_id: str,
        replacement: SourceRecord,
        *,
        runtime_path: Path | None = None,
        index_path: Path | None = None,
    ) -> None:
        if source_id == replacement.source_id:
            raise ValueError("a source cannot supersede itself")
        self.register(replacement)
        if runtime_path is not None or index_path is not None:
            self.attach_installation(
                replacement.source_id, runtime_path=runtime_path, index_path=index_path
            )
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute(
                "SELECT state FROM source_records WHERE source_id=?", (source_id,)
            ).fetchone()
            if old is None:
                raise KeyError(f"unknown source: {source_id}")
            connection.execute(
                "UPDATE source_records SET state='superseded',updated_at_us=? WHERE source_id=?",
                (self._now(), source_id),
            )
            connection.execute(
                """INSERT INTO source_installations(source_id,replacement_source_id) VALUES(?,?)
                ON CONFLICT(source_id) DO UPDATE SET replacement_source_id=excluded.replacement_source_id""",
                (source_id, replacement.source_id),
            )
            self._event(
                connection,
                source_id,
                "supersede",
                old[0],
                SourceState.SUPERSEDED.value,
                {"replacement_source_id": replacement.source_id},
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def add_dependency(self, source_id: str, depends_on_source_id: str) -> None:
        """Declare that source_id requires depends_on_source_id to remain usable."""
        if source_id == depends_on_source_id:
            raise ValueError("a source cannot depend on itself")
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            known = {
                str(row[0])
                for row in connection.execute(
                    "SELECT source_id FROM source_records WHERE source_id IN (?,?)",
                    (source_id, depends_on_source_id),
                ).fetchall()
            }
            missing = sorted({source_id, depends_on_source_id} - known)
            if missing:
                raise KeyError(f"unknown source: {', '.join(missing)}")
            connection.execute(
                "INSERT OR IGNORE INTO source_dependencies(source_id,depends_on_source_id) VALUES(?,?)",
                (source_id, depends_on_source_id),
            )
            self._event(
                connection,
                source_id,
                "dependency_add",
                None,
                None,
                {"depends_on_source_id": depends_on_source_id},
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def dependencies(self, source_id: str) -> tuple[str, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT depends_on_source_id FROM source_dependencies WHERE source_id=? ORDER BY depends_on_source_id",
                (source_id,),
            ).fetchall()
            return tuple(str(row[0]) for row in rows)
        finally:
            connection.close()

    def dependents(self, source_id: str, *, active_only: bool = False) -> tuple[str, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            sql = """SELECT d.source_id FROM source_dependencies d
                JOIN source_records s ON s.source_id=d.source_id
                WHERE d.depends_on_source_id=?"""
            parameters: tuple[object, ...] = (source_id,)
            if active_only:
                sql += " AND s.state IN ('installed','offline','update_available')"
            sql += " ORDER BY d.source_id"
            return tuple(str(row[0]) for row in connection.execute(sql, parameters).fetchall())
        finally:
            connection.close()

    def activation_blockers(self, source_id: str) -> tuple[str, ...]:
        blockers = []
        for dependency_id in self.dependencies(source_id):
            state = self.get(dependency_id).state
            if state not in {
                SourceState.INSTALLED,
                SourceState.OFFLINE,
                SourceState.UPDATE_AVAILABLE,
            }:
                blockers.append(f"{dependency_id} ({state.value})")
        return tuple(blockers)

    def activate(self, source_id: str) -> None:
        blockers = self.activation_blockers(source_id)
        if blockers:
            raise RuntimeError("source dependencies are unavailable: " + ", ".join(blockers))
        state = self.verify_installation(source_id)
        if state is SourceState.MISSING:
            raise FileNotFoundError(
                self.installation(source_id).last_error or "source files are missing"
            )
        self.set_state(source_id, SourceState.INSTALLED, reason="activated")

    def lifecycle_events(self, source_id: str) -> tuple[dict, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT action,from_state,to_state,details_json,created_at_us FROM source_lifecycle_events WHERE source_id=? ORDER BY id",
                (source_id,),
            ).fetchall()
            return tuple(
                {
                    "action": r[0],
                    "from_state": r[1],
                    "to_state": r[2],
                    "details": json.loads(r[3]),
                    "created_at_us": int(r[4]),
                }
                for r in rows
            )
        finally:
            connection.close()

    def remove(self, source_id: str, options: SourceRemovalOptions) -> None:
        active_dependents = self.dependents(source_id, active_only=True)
        if active_dependents:
            raise RuntimeError(
                "source is required by active dependents: " + ", ".join(active_dependents)
            )
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM source_records WHERE source_id=?", (source_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown source: {source_id}")
            if options.delete_pending_results:
                connection.execute(
                    "DELETE FROM enrichment_records WHERE source_id=? AND status IN ('generated','pending_review')",
                    (source_id,),
                )
            if options.delete_rejected_results:
                connection.execute(
                    "DELETE FROM enrichment_records WHERE source_id=? AND status='rejected'",
                    (source_id,),
                )
            if options.delete_accepted_enrichment:
                connection.execute(
                    "DELETE FROM enrichment_records WHERE source_id=? AND status='accepted'",
                    (source_id,),
                )
            connection.execute(
                "UPDATE source_records SET state='removed',updated_at_us=? WHERE source_id=?",
                (self._now(), source_id),
            )
            self._event(
                connection,
                source_id,
                "remove",
                row[0],
                SourceState.REMOVED.value,
                {
                    "options": options.__dict__
                    if hasattr(options, "__dict__")
                    else {k: getattr(options, k) for k in options.__slots__}
                },
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def list(self) -> tuple[SourceRecord, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT source_id,kind,display_name,version,state,licence,attribution,checksum FROM source_records ORDER BY display_name COLLATE NOCASE,source_id"
            ).fetchall()
            return tuple(
                SourceRecord(
                    str(r[0]),
                    str(r[1]),
                    str(r[2]),
                    str(r[3]),
                    SourceState(str(r[4])),
                    r[5],
                    r[6],
                    r[7],
                )
                for r in rows
            )
        finally:
            connection.close()

    def enrichment_counts(self, source_id: str) -> dict[str, int]:
        connection = self._factory.connect(read_only=True)
        try:
            return {
                str(s): int(c)
                for s, c in connection.execute(
                    "SELECT status,COUNT(*) FROM enrichment_records WHERE source_id=? GROUP BY status",
                    (source_id,),
                ).fetchall()
            }
        finally:
            connection.close()

    def get(self, source_id: str) -> SourceRecord:
        connection = self._factory.connect(read_only=True)
        try:
            r = connection.execute(
                "SELECT source_id,kind,display_name,version,state,licence,attribution,checksum FROM source_records WHERE source_id=?",
                (source_id,),
            ).fetchone()
            if r is None:
                raise KeyError(f"unknown source: {source_id}")
            return SourceRecord(
                str(r[0]), str(r[1]), str(r[2]), str(r[3]), SourceState(str(r[4])), r[5], r[6], r[7]
            )
        finally:
            connection.close()
