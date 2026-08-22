"""SQLite persistence for resumable original-file export plans."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from natureai_next.domain.exporting import (
    ExportItemState,
    ExportPlanState,
    OriginalFileExportPlan,
    PersistedOriginalExportItem,
    PersistedOriginalExportPlan,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


class SqliteResumableOriginalExportStore:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def prepare(
        self,
        *,
        plan: OriginalFileExportPlan,
        items: tuple[PersistedOriginalExportItem, ...],
        now_us: int,
    ) -> PersistedOriginalExportPlan:
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM export_plans WHERE public_id=?", (plan.public_id,)
            ).fetchone()
            plan_json = _plan_json(plan)
            if existing is not None:
                if existing["plan_json"] != plan_json:
                    raise ValueError("export plan identity already exists with different content")
                connection.execute("COMMIT")
                return _plan(existing)
            cursor = connection.execute(
                """INSERT INTO export_plans(public_id,export_kind,schema_version,destination_path,plan_json,state,created_at_us,modified_at_us)
                VALUES(?, 'original_files', 1, ?, ?, 'prepared', ?, ?)""",
                (
                    plan.public_id,
                    str(plan.destination_directory),
                    plan_json,
                    plan.created_at_us,
                    now_us,
                ),
            )
            plan_id = int(cursor.lastrowid)
            connection.executemany(
                """INSERT INTO export_plan_items(
                    export_plan_id,asset_public_id,item_order,source_path,source_size_bytes,source_sha256,
                    relative_output_path,state,attempt_count,modified_at_us
                ) VALUES(?,?,?,?,?,?,?,'pending',0,?)""",
                [
                    (
                        plan_id,
                        item.asset_public_id,
                        item.item_order,
                        str(item.source_path),
                        item.source_size_bytes,
                        item.source_sha256,
                        item.relative_output_path,
                        now_us,
                    )
                    for item in items
                ],
            )
            row = connection.execute("SELECT * FROM export_plans WHERE id=?", (plan_id,)).fetchone()
            connection.execute("COMMIT")
            return _plan(row)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def get_plan(self, public_id: str) -> PersistedOriginalExportPlan | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT * FROM export_plans WHERE public_id=?", (public_id,)
            ).fetchone()
            return None if row is None else _plan(row)
        finally:
            connection.close()

    def list_items(self, plan_public_id: str) -> tuple[PersistedOriginalExportItem, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                """SELECT i.* FROM export_plan_items i JOIN export_plans p ON p.id=i.export_plan_id
                WHERE p.public_id=? ORDER BY i.item_order,i.id""",
                (plan_public_id,),
            ).fetchall()
            return tuple(_item(row) for row in rows)
        finally:
            connection.close()

    def claim_next_item(
        self, plan_public_id: str, now_us: int
    ) -> PersistedOriginalExportItem | None:
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT i.id FROM export_plan_items i JOIN export_plans p ON p.id=i.export_plan_id
                WHERE p.public_id=? AND i.state='pending'
                ORDER BY i.item_order,i.id LIMIT 1""",
                (plan_public_id,),
            ).fetchone()
            if row is None:
                connection.execute("COMMIT")
                return None
            connection.execute(
                "UPDATE export_plan_items SET state='running',attempt_count=attempt_count+1,error_text=NULL,modified_at_us=? WHERE id=?",
                (now_us, row["id"]),
            )
            claimed = connection.execute(
                "SELECT * FROM export_plan_items WHERE id=?", (row["id"],)
            ).fetchone()
            connection.execute("COMMIT")
            return _item(claimed)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def mark_item_succeeded(self, item_id: int, *, size: int, sha256: str, now_us: int) -> None:
        self._update_item(item_id, "succeeded", now_us, size=size, sha256=sha256)

    def mark_item_failed(self, item_id: int, *, error_text: str, now_us: int) -> None:
        self._update_item(item_id, "failed", now_us, error_text=error_text[:2000])

    def _update_item(
        self,
        item_id: int,
        state: str,
        now_us: int,
        *,
        size: int | None = None,
        sha256: str | None = None,
        error_text: str | None = None,
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                """UPDATE export_plan_items SET state=?,output_size_bytes=?,output_sha256=?,error_text=?,modified_at_us=?
                WHERE id=?""",
                (state, size, sha256, error_text, now_us, item_id),
            )
        finally:
            connection.close()

    def recover_running_items(self, plan_public_id: str, now_us: int) -> int:
        connection = self._factory.connect()
        try:
            cursor = connection.execute(
                """UPDATE export_plan_items SET state='pending',modified_at_us=? WHERE state='running'
                AND export_plan_id=(SELECT id FROM export_plans WHERE public_id=?)""",
                (now_us, plan_public_id),
            )
            return cursor.rowcount
        finally:
            connection.close()

    def retry_failed_items(self, plan_public_id: str, now_us: int) -> int:
        connection = self._factory.connect()
        try:
            cursor = connection.execute(
                """UPDATE export_plan_items SET state='pending',modified_at_us=? WHERE state='failed'
                AND export_plan_id=(SELECT id FROM export_plans WHERE public_id=?)""",
                (now_us, plan_public_id),
            )
            return cursor.rowcount
        finally:
            connection.close()

    def mark_plan_running(self, plan_public_id: str, now_us: int) -> None:
        self._update_plan(plan_public_id, "running", now_us)

    def mark_plan_succeeded(
        self,
        plan_public_id: str,
        *,
        manifest_path: Path | None,
        manifest_sha256: str | None,
        now_us: int,
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                """UPDATE export_plans SET state='succeeded',modified_at_us=?,completed_at_us=?,manifest_path=?,manifest_sha256=?,error_text=NULL
                WHERE public_id=?""",
                (
                    now_us,
                    now_us,
                    None if manifest_path is None else str(manifest_path),
                    manifest_sha256,
                    plan_public_id,
                ),
            )
        finally:
            connection.close()

    def mark_plan_failed(self, plan_public_id: str, *, error_text: str, now_us: int) -> None:
        self._update_plan(plan_public_id, "failed", now_us, error_text=error_text[:2000])

    def _update_plan(
        self, public_id: str, state: str, now_us: int, error_text: str | None = None
    ) -> None:
        connection = self._factory.connect()
        try:
            connection.execute(
                "UPDATE export_plans SET state=?,modified_at_us=?,error_text=? WHERE public_id=?",
                (state, now_us, error_text, public_id),
            )
        finally:
            connection.close()


def _plan_json(plan: OriginalFileExportPlan) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "destination_directory": str(plan.destination_directory),
            "selection": {
                "asset_public_ids": list(plan.selection.asset_public_ids),
                "include_all_active": plan.selection.include_all_active,
            },
            "naming_template": plan.naming_template,
            "collision_policy": plan.collision_policy.value,
            "include_manifest": plan.include_manifest,
            "verify_source_checksum": plan.verify_source_checksum,
            "created_at_us": plan.created_at_us,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _plan(row: sqlite3.Row) -> PersistedOriginalExportPlan:
    return PersistedOriginalExportPlan(
        id=row["id"],
        public_id=row["public_id"],
        destination_directory=Path(row["destination_path"]),
        plan_json=row["plan_json"],
        state=ExportPlanState(row["state"]),
        created_at_us=row["created_at_us"],
        modified_at_us=row["modified_at_us"],
        manifest_path=None if row["manifest_path"] is None else Path(row["manifest_path"]),
        manifest_sha256=row["manifest_sha256"],
        error_text=row["error_text"],
    )


def _item(row: sqlite3.Row) -> PersistedOriginalExportItem:
    return PersistedOriginalExportItem(
        id=row["id"],
        asset_public_id=row["asset_public_id"],
        item_order=row["item_order"],
        source_path=Path(row["source_path"]),
        source_size_bytes=row["source_size_bytes"],
        source_sha256=row["source_sha256"],
        relative_output_path=row["relative_output_path"],
        state=ExportItemState(row["state"]),
        attempt_count=row["attempt_count"],
        output_size_bytes=row["output_size_bytes"],
        output_sha256=row["output_sha256"],
        error_text=row["error_text"],
    )
