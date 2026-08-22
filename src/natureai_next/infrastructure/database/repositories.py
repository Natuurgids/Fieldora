"""SQLite repository adapters."""

from __future__ import annotations

import sqlite3
from dataclasses import replace

from natureai_next.domain.catalog import (
    Asset,
    AssetLifecycle,
    AvailabilityState,
    Collection,
    FileInstance,
    FileRole,
    MediaType,
    StorageMode,
    Tag,
)
from natureai_next.domain.events import AuditEntry, OutboxEvent
from natureai_next.domain.jobs import JobRecord, JobState


class SqliteAssetRepository:
    def __init__(self, c: sqlite3.Connection) -> None:
        self.c = c

    def add(self, a: Asset) -> Asset:
        cur = self.c.execute(
            "INSERT INTO assets(public_id,media_type,lifecycle_state,rating,title,caption,user_notes,created_at_us,modified_at_us,revision) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                a.public_id,
                a.media_type,
                a.lifecycle_state,
                a.rating,
                a.title,
                a.caption,
                a.user_notes,
                a.created_at_us,
                a.modified_at_us,
                a.revision,
            ),
        )
        return replace(a, id=int(cur.lastrowid))

    def get_by_public_id(self, public_id: str) -> Asset | None:
        r = self.c.execute("SELECT * FROM assets WHERE public_id=?", (public_id,)).fetchone()
        return None if r is None else _asset(r)

    def list_page(self, *, limit: int, after_id: int | None = None) -> tuple[Asset, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self.c.execute(
            "SELECT * FROM assets WHERE lifecycle_state='active' AND id>? ORDER BY id LIMIT ?",
            (after_id or 0, limit),
        )
        return tuple(_asset(r) for r in rows)


def _asset(r: sqlite3.Row) -> Asset:
    return Asset(
        id=r["id"],
        public_id=r["public_id"],
        media_type=MediaType(r["media_type"]),
        lifecycle_state=AssetLifecycle(r["lifecycle_state"]),
        rating=r["rating"],
        title=r["title"],
        caption=r["caption"],
        user_notes=r["user_notes"],
        created_at_us=r["created_at_us"],
        modified_at_us=r["modified_at_us"],
        revision=r["revision"],
    )


class SqliteFileInstanceRepository:
    def __init__(self, c: sqlite3.Connection) -> None:
        self.c = c

    def add(self, f: FileInstance) -> FileInstance:
        cur = self.c.execute(
            "INSERT INTO file_instances(public_id,asset_id,storage_mode,role,normalized_path,path_key,file_size,modified_at_observed_us,sha256,availability_state,mime_type,format_name,created_at_us,modified_at_us) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f.public_id,
                f.asset_id,
                f.storage_mode,
                f.role,
                f.normalized_path,
                f.path_key,
                f.file_size,
                f.modified_at_observed_us,
                f.sha256,
                f.availability_state,
                f.mime_type,
                f.format_name,
                f.created_at_us,
                f.modified_at_us,
            ),
        )
        return replace(f, id=int(cur.lastrowid))

    def find_by_sha256(self, sha256: str) -> tuple[FileInstance, ...]:
        return tuple(
            _file(r)
            for r in self.c.execute(
                "SELECT * FROM file_instances WHERE sha256=? ORDER BY id", (sha256,)
            )
        )


def _file(r: sqlite3.Row) -> FileInstance:
    return FileInstance(
        id=r["id"],
        public_id=r["public_id"],
        asset_id=r["asset_id"],
        storage_mode=StorageMode(r["storage_mode"]),
        role=FileRole(r["role"]),
        normalized_path=r["normalized_path"],
        path_key=r["path_key"],
        file_size=r["file_size"],
        modified_at_observed_us=r["modified_at_observed_us"],
        sha256=r["sha256"],
        availability_state=AvailabilityState(r["availability_state"]),
        mime_type=r["mime_type"],
        format_name=r["format_name"],
        created_at_us=r["created_at_us"],
        modified_at_us=r["modified_at_us"],
    )


class SqliteTagRepository:
    def __init__(self, c: sqlite3.Connection) -> None:
        self.c = c

    def add(self, t: Tag) -> Tag:
        cur = self.c.execute(
            "INSERT INTO tags(public_id,normalized_name,display_name,parent_tag_id,color,created_at_us) VALUES(?,?,?,?,?,?)",
            (
                t.public_id,
                t.normalized_name,
                t.display_name,
                t.parent_tag_id,
                t.color,
                t.created_at_us,
            ),
        )
        return replace(t, id=int(cur.lastrowid))

    def attach(self, *, asset_id: int, tag_id: int, source: str, created_at_us: int) -> None:
        self.c.execute(
            "INSERT OR IGNORE INTO asset_tags VALUES(?,?,?,?)",
            (asset_id, tag_id, source, created_at_us),
        )


class SqliteCollectionRepository:
    def __init__(self, c: sqlite3.Connection) -> None:
        self.c = c

    def add(self, x: Collection) -> Collection:
        cur = self.c.execute(
            "INSERT INTO collections(public_id,collection_type,name,description,smart_query_json,query_schema_version,sort_mode,created_at_us,modified_at_us) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                x.public_id,
                x.collection_type,
                x.name,
                x.description,
                x.smart_query_json,
                x.query_schema_version,
                x.sort_mode,
                x.created_at_us,
                x.modified_at_us,
            ),
        )
        return replace(x, id=int(cur.lastrowid))

    def add_asset(
        self, *, collection_id: int, asset_id: int, position_key: str, added_at_us: int
    ) -> None:
        self.c.execute(
            "INSERT INTO collection_assets VALUES(?,?,?,?)",
            (collection_id, asset_id, position_key, added_at_us),
        )


class SqliteOutboxRepository:
    def __init__(self, c: sqlite3.Connection) -> None:
        self.c = c

    def add(self, e: OutboxEvent) -> OutboxEvent:
        cur = self.c.execute(
            "INSERT INTO event_outbox(public_id,event_type,schema_version,aggregate_public_id,payload_json,created_at_us,dispatch_state,attempt_count) VALUES(?,?,?,?,?,?,?,?)",
            (
                e.public_id,
                e.event_type,
                e.schema_version,
                e.aggregate_public_id,
                e.payload_json,
                e.created_at_us,
                e.dispatch_state,
                e.attempt_count,
            ),
        )
        return replace(e, id=int(cur.lastrowid))


class SqliteAuditRepository:
    def __init__(self, c: sqlite3.Connection) -> None:
        self.c = c

    def add(self, e: AuditEntry) -> AuditEntry:
        cur = self.c.execute(
            "INSERT INTO audit_log(public_id,actor,action_type,target_public_id,before_json,after_json,created_at_us,correlation_id) VALUES(?,?,?,?,?,?,?,?)",
            (
                e.public_id,
                e.actor,
                e.action_type,
                e.target_public_id,
                e.before_json,
                e.after_json,
                e.created_at_us,
                e.correlation_id,
            ),
        )
        return replace(e, id=int(cur.lastrowid))


# Milestone 3 durable job adapter. This definition intentionally supersedes the
# foundational insert-only adapter above while preserving its public name.
class SqliteJobRepository:
    def __init__(self, c: sqlite3.Connection) -> None:
        self.c = c

    def add(self, j: JobRecord) -> JobRecord:
        cur = self.c.execute(
            """INSERT INTO jobs(
                public_id,job_type,payload_version,payload_json,state,priority,resource_class,
                idempotency_key,parent_job_id,dependency_job_id,progress_current,progress_total,
                progress_unit,progress_message,attempt_count,retry_at_us,created_at_us,started_at_us,
                completed_at_us,modified_at_us,error_code,diagnostic_reference,result_json,
                cancellation_requested,pause_requested,lease_owner,lease_expires_at_us
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                j.public_id,
                j.job_type,
                j.payload_version,
                j.payload_json,
                j.state,
                j.priority,
                j.resource_class,
                j.idempotency_key,
                j.parent_job_id,
                j.dependency_job_id,
                j.progress_current,
                j.progress_total,
                j.progress_unit,
                j.progress_message,
                j.attempt_count,
                j.retry_at_us,
                j.created_at_us,
                j.started_at_us,
                j.completed_at_us,
                j.modified_at_us,
                j.error_code,
                j.diagnostic_reference,
                j.result_json,
                int(j.cancellation_requested),
                int(j.pause_requested),
                j.lease_owner,
                j.lease_expires_at_us,
            ),
        )
        return replace(j, id=int(cur.lastrowid))

    def get(self, public_id: str) -> JobRecord | None:
        row = self.c.execute("SELECT * FROM jobs WHERE public_id=?", (public_id,)).fetchone()
        return None if row is None else _job(row)

    def claim_next(
        self, *, resource_class: str, worker_id: str, now_us: int, lease_until_us: int
    ) -> JobRecord | None:
        row = self.c.execute(
            """SELECT j.id FROM jobs j
               WHERE j.state='queued' AND j.resource_class=?
                 AND (j.retry_at_us IS NULL OR j.retry_at_us<=?)
                 AND (j.dependency_job_id IS NULL OR EXISTS(
                     SELECT 1 FROM jobs d WHERE d.id=j.dependency_job_id AND d.state='succeeded'))
               ORDER BY j.priority DESC,j.created_at_us,j.id LIMIT 1""",
            (resource_class, now_us),
        ).fetchone()
        if row is None:
            return None
        updated = self.c.execute(
            """UPDATE jobs SET state='running',started_at_us=COALESCE(started_at_us,?),
               modified_at_us=?,attempt_count=attempt_count+1,lease_owner=?,lease_expires_at_us=?
               WHERE id=? AND state='queued'""",
            (now_us, now_us, worker_id, lease_until_us, row["id"]),
        )
        if updated.rowcount != 1:
            return None
        claimed = self.c.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
        return _job(claimed)

    def update_progress(
        self,
        public_id: str,
        *,
        current: int,
        total: int | None,
        unit: str | None,
        message: str | None,
        now_us: int,
    ) -> None:
        if current < 0 or (total is not None and (total < 0 or current > total)):
            raise ValueError("invalid job progress")
        self.c.execute(
            "UPDATE jobs SET progress_current=?,progress_total=?,progress_unit=?,progress_message=?,modified_at_us=? WHERE public_id=? AND state='running'",
            (current, total, unit, message, now_us, public_id),
        )

    def request_cancel(self, public_id: str, now_us: int) -> bool:
        cur = self.c.execute(
            "UPDATE jobs SET cancellation_requested=1,modified_at_us=? WHERE public_id=? AND state IN ('queued','running','paused','interrupted','failed')",
            (now_us, public_id),
        )
        self.c.execute(
            "UPDATE jobs SET state='cancelled',completed_at_us=?,lease_owner=NULL,lease_expires_at_us=NULL WHERE public_id=? AND state IN ('queued','paused','interrupted','failed')",
            (now_us, public_id),
        )
        return cur.rowcount > 0

    def request_pause(self, public_id: str, now_us: int) -> bool:
        cur = self.c.execute(
            "UPDATE jobs SET pause_requested=1,modified_at_us=? WHERE public_id=? AND state IN ('queued','running')",
            (now_us, public_id),
        )
        self.c.execute(
            "UPDATE jobs SET state='paused' WHERE public_id=? AND state='queued'", (public_id,)
        )
        return cur.rowcount > 0

    def resume(self, public_id: str, now_us: int) -> bool:
        cur = self.c.execute(
            "UPDATE jobs SET state='queued',pause_requested=0,cancellation_requested=0,retry_at_us=NULL,modified_at_us=? WHERE public_id=? AND state IN ('paused','interrupted','failed')",
            (now_us, public_id),
        )
        return cur.rowcount == 1

    def finish(
        self,
        public_id: str,
        *,
        state: JobState,
        now_us: int,
        result_json: str | None = None,
        error_code: str | None = None,
        retry_at_us: int | None = None,
    ) -> None:
        if state not in {
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.PAUSED,
            JobState.QUEUED,
        }:
            raise ValueError("unsupported completion state")
        completed = (
            now_us if state in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED} else None
        )
        self.c.execute(
            """UPDATE jobs SET state=?,result_json=?,error_code=?,retry_at_us=?,completed_at_us=?,modified_at_us=?,lease_owner=NULL,lease_expires_at_us=NULL WHERE public_id=? AND state='running'""",
            (state, result_json, error_code, retry_at_us, completed, now_us, public_id),
        )

    def recover_expired(self, *, now_us: int) -> int:
        cur = self.c.execute(
            """UPDATE jobs SET state='interrupted',modified_at_us=?,lease_owner=NULL,lease_expires_at_us=NULL,error_code='worker_interrupted' WHERE state='running' AND lease_expires_at_us IS NOT NULL AND lease_expires_at_us<=?""",
            (now_us, now_us),
        )
        self.c.execute(
            "UPDATE job_items SET state='pending',modified_at_us=? WHERE state='running' AND job_id IN (SELECT id FROM jobs WHERE state='interrupted')",
            (now_us,),
        )
        return cur.rowcount

    def list_recent(self, limit: int = 100) -> tuple[JobRecord, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        return tuple(
            _job(row)
            for row in self.c.execute(
                "SELECT * FROM jobs ORDER BY created_at_us DESC,id DESC LIMIT ?", (limit,)
            )
        )


def _job(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        id=row["id"],
        public_id=row["public_id"],
        job_type=row["job_type"],
        payload_version=row["payload_version"],
        payload_json=row["payload_json"],
        state=JobState(row["state"]),
        priority=row["priority"],
        resource_class=row["resource_class"],
        idempotency_key=row["idempotency_key"],
        parent_job_id=row["parent_job_id"],
        dependency_job_id=row["dependency_job_id"],
        progress_current=row["progress_current"],
        progress_total=row["progress_total"],
        progress_unit=row["progress_unit"],
        progress_message=row["progress_message"],
        attempt_count=row["attempt_count"],
        retry_at_us=row["retry_at_us"],
        created_at_us=row["created_at_us"],
        started_at_us=row["started_at_us"],
        completed_at_us=row["completed_at_us"],
        modified_at_us=row["modified_at_us"],
        error_code=row["error_code"],
        diagnostic_reference=row["diagnostic_reference"],
        result_json=row["result_json"],
        cancellation_requested=bool(row["cancellation_requested"]),
        pause_requested=bool(row["pause_requested"]),
        lease_owner=row["lease_owner"],
        lease_expires_at_us=row["lease_expires_at_us"],
    )
