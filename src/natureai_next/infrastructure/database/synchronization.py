"""SQLite persistence for Phase E desktop synchronization configuration."""

from __future__ import annotations

import json

from natureai_next.domain.synchronization import (
    EnrollmentState,
    PlatformAccount,
    ProjectEnrollment,
    RegisteredDesktopDevice,
    SyncChange,
    SyncConflict,
    SyncItemState,
    MediaTransfer,
    ContributionAcknowledgment,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


class SqliteDesktopSynchronizationRepository:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def put_account(self, account: PlatformAccount) -> None:
        with self._factory.connect() as connection:
            connection.execute(
                "INSERT INTO sync_accounts VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(account_id) DO UPDATE SET endpoint_url=excluded.endpoint_url,"
                "display_name=excluded.display_name,organization_id=excluded.organization_id,"
                "subject_id=excluded.subject_id",
                (account.account_id, account.endpoint_url, account.display_name,
                 account.organization_id, account.subject_id, account.created_at_utc),
            )

    def accounts(self) -> tuple[PlatformAccount, ...]:
        with self._factory.connect() as connection:
            rows = connection.execute("SELECT * FROM sync_accounts ORDER BY display_name").fetchall()
        return tuple(PlatformAccount(**dict(row)) for row in rows)

    def put_device(self, device: RegisteredDesktopDevice) -> None:
        with self._factory.connect() as connection:
            connection.execute(
                "INSERT INTO sync_devices VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(device_id) DO UPDATE SET server_device_id=excluded.server_device_id,"
                "display_name=excluded.display_name,revoked_at_utc=excluded.revoked_at_utc",
                (device.device_id, device.account_id, device.server_device_id,
                 device.display_name, device.registered_at_utc, device.revoked_at_utc),
            )

    def devices(self, account_id: str) -> tuple[RegisteredDesktopDevice, ...]:
        with self._factory.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sync_devices WHERE account_id=? ORDER BY registered_at_utc",
                (account_id,),
            ).fetchall()
        return tuple(RegisteredDesktopDevice(**dict(row)) for row in rows)

    def put_enrollment(self, enrollment: ProjectEnrollment) -> None:
        with self._factory.connect() as connection:
            connection.execute(
                "INSERT INTO sync_project_enrollments VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(account_id,project_id) DO UPDATE SET contract_id=excluded.contract_id,"
                "state=excluded.state,rights_json=excluded.rights_json,"
                "expires_at_utc=excluded.expires_at_utc,revision=excluded.revision,"
                "acknowledged_at_utc=excluded.acknowledged_at_utc "
                "WHERE excluded.revision>=sync_project_enrollments.revision",
                (enrollment.enrollment_id, enrollment.account_id, enrollment.project_id,
                 enrollment.contract_id, enrollment.state.value,
                 json.dumps(enrollment.rights), enrollment.expires_at_utc,
                 enrollment.revision, enrollment.acknowledged_at_utc),
            )

    def enrollments(self, account_id: str) -> tuple[ProjectEnrollment, ...]:
        with self._factory.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sync_project_enrollments WHERE account_id=? ORDER BY project_id",
                (account_id,),
            ).fetchall()
        return tuple(
            ProjectEnrollment(
                row["enrollment_id"], row["account_id"], row["project_id"],
                row["contract_id"], EnrollmentState(row["state"]),
                tuple(json.loads(row["rights_json"])), row["expires_at_utc"],
                row["revision"], row["acknowledged_at_utc"],
            )
            for row in rows
        )

    @staticmethod
    def _change(row) -> SyncChange:
        return SyncChange(
            row["change_id"], row["enrollment_id"], row["idempotency_key"],
            row["aggregate_type"], row["aggregate_id"], row["base_revision"],
            json.loads(row["payload_json"]), bool(row["tombstone"]),
            SyncItemState(row["state"]), row["attempt_count"],
            row["next_attempt_at_utc"], row["lease_until_utc"],
        )

    def enqueue_outbox(self, change: SyncChange) -> bool:
        with self._factory.connect() as connection:
            result = connection.execute(
                "INSERT OR IGNORE INTO sync_outbox VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (change.change_id, change.enrollment_id, change.idempotency_key,
                 change.aggregate_type, change.aggregate_id, change.base_revision,
                 json.dumps(change.payload, separators=(",", ":"), sort_keys=True),
                 int(change.tombstone), change.state.value, change.attempt_count,
                 change.next_attempt_at_utc, change.lease_until_utc),
            )
            return result.rowcount == 1

    def claim_outbox(
        self, *, enrollment_id: str, now_utc: str, lease_until_utc: str, limit: int
    ) -> tuple[SyncChange, ...]:
        if not 1 <= limit <= 500:
            raise ValueError("claim limit must be between 1 and 500")
        with self._factory.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT change_id FROM sync_outbox WHERE enrollment_id=? AND ("
                "((state IN ('pending','retry') AND (next_attempt_at_utc='' OR next_attempt_at_utc<=?)) "
                "OR (state='inflight' AND lease_until_utc<?))) ORDER BY change_id LIMIT ?",
                (enrollment_id, now_utc, now_utc, limit),
            ).fetchall()
            ids = tuple(row["change_id"] for row in rows)
            if ids:
                marks = ",".join("?" for _ in ids)
                connection.execute(
                    f"UPDATE sync_outbox SET state='inflight',attempt_count=attempt_count+1,"
                    f"lease_until_utc=? WHERE change_id IN ({marks})",
                    (lease_until_utc, *ids),
                )
            connection.execute("COMMIT")
            if not ids:
                return ()
            marks = ",".join("?" for _ in ids)
            claimed = connection.execute(
                f"SELECT * FROM sync_outbox WHERE change_id IN ({marks}) ORDER BY change_id", ids
            ).fetchall()
        return tuple(self._change(row) for row in claimed)

    def retry_outbox(self, change_id: str, *, next_attempt_at_utc: str) -> None:
        with self._factory.connect() as connection:
            connection.execute(
                "UPDATE sync_outbox SET state='retry',next_attempt_at_utc=?,lease_until_utc='' "
                "WHERE change_id=? AND state='inflight'",
                (next_attempt_at_utc, change_id),
            )

    def complete_outbox(self, change_id: str) -> None:
        with self._factory.connect() as connection:
            connection.execute(
                "UPDATE sync_outbox SET state='applied',lease_until_utc='' WHERE change_id=?",
                (change_id,),
            )

    def stop_outbox(self, change_id: str, *, state: str) -> None:
        if state not in {"conflict", "rejected"}:
            raise ValueError("outbox terminal state must be conflict or rejected")
        with self._factory.connect() as connection:
            connection.execute(
                "UPDATE sync_outbox SET state=?,lease_until_utc='' WHERE change_id=?",
                (state, change_id),
            )

    def accept_inbox(self, change: SyncChange) -> bool:
        with self._factory.connect() as connection:
            result = connection.execute(
                "INSERT OR IGNORE INTO sync_inbox(change_id,enrollment_id,idempotency_key,"
                "aggregate_type,aggregate_id,base_revision,payload_json,tombstone) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (change.change_id, change.enrollment_id, change.idempotency_key,
                 change.aggregate_type, change.aggregate_id, change.base_revision,
                 json.dumps(change.payload, separators=(",", ":"), sort_keys=True),
                 int(change.tombstone)),
            )
            return result.rowcount == 1

    def put_cursor(self, enrollment_id: str, cursor: str) -> None:
        with self._factory.connect() as connection:
            connection.execute(
                "INSERT INTO sync_cursors VALUES(?,?) ON CONFLICT(enrollment_id) "
                "DO UPDATE SET cursor=excluded.cursor", (enrollment_id, cursor)
            )

    def cursor(self, enrollment_id: str) -> str:
        with self._factory.connect() as connection:
            row = connection.execute(
                "SELECT cursor FROM sync_cursors WHERE enrollment_id=?", (enrollment_id,)
            ).fetchone()
        return "" if row is None else str(row["cursor"])

    def put_conflict(self, conflict: SyncConflict) -> None:
        with self._factory.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO sync_conflicts("
                "conflict_id,enrollment_id,aggregate_type,aggregate_id,"
                "local_revision,remote_revision,local_payload_json,"
                "remote_payload_json,created_at_utc,resolved_at_utc"
                ") VALUES(?,?,?,?,?,?,?,?,?,?)",
                (conflict.conflict_id, conflict.enrollment_id, conflict.aggregate_type,
                 conflict.aggregate_id, conflict.local_revision, conflict.remote_revision,
                 json.dumps(conflict.local_payload, sort_keys=True),
                 json.dumps(conflict.remote_payload, sort_keys=True),
                 conflict.created_at_utc, conflict.resolved_at_utc),
            )

    def conflicts(self, enrollment_id: str) -> tuple[SyncConflict, ...]:
        with self._factory.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sync_conflicts WHERE enrollment_id=? AND resolved_at_utc='' "
                "ORDER BY created_at_utc,conflict_id", (enrollment_id,)
            ).fetchall()
        return tuple(
            SyncConflict(
                row["conflict_id"], row["enrollment_id"], row["aggregate_type"],
                row["aggregate_id"], row["local_revision"], row["remote_revision"],
                json.loads(row["local_payload_json"]), json.loads(row["remote_payload_json"]),
                row["created_at_utc"], row["resolved_at_utc"],
            )
            for row in rows
        )

    def put_media_transfer(self, transfer: MediaTransfer) -> None:
        with self._factory.connect() as connection:
            connection.execute(
                "INSERT INTO sync_media_transfers VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(transfer_id) DO UPDATE SET offset=excluded.offset,"
                "state=excluded.state,etag=excluded.etag",
                (transfer.transfer_id, transfer.enrollment_id, transfer.media_id,
                 transfer.destination_path, transfer.expected_size,
                 transfer.expected_sha256, transfer.etag, transfer.offset, transfer.state),
            )

    def media_transfer(self, transfer_id: str) -> MediaTransfer | None:
        with self._factory.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sync_media_transfers WHERE transfer_id=?", (transfer_id,)
            ).fetchone()
        return None if row is None else MediaTransfer(**dict(row))

    def acknowledge_contribution(self, acknowledgment: ContributionAcknowledgment) -> None:
        with self._factory.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO sync_contribution_acknowledgments VALUES(?,?,?,?,?,?,?)",
                (acknowledgment.acknowledgment_id, acknowledgment.enrollment_id,
                 acknowledgment.enrollment_revision, acknowledgment.license_id,
                 acknowledgment.terms_sha256, acknowledgment.acknowledged_by,
                 acknowledgment.acknowledged_at_utc),
            )

    def has_current_acknowledgment(self, enrollment_id: str, revision: int) -> bool:
        with self._factory.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM sync_contribution_acknowledgments "
                "WHERE enrollment_id=? AND enrollment_revision=? LIMIT 1",
                (enrollment_id, revision),
            ).fetchone()
        return row is not None

    def pending_outbox(self, enrollment_id: str) -> tuple[SyncChange, ...]:
        with self._factory.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sync_outbox WHERE enrollment_id=? "
                "AND state IN ('pending','retry') ORDER BY change_id", (enrollment_id,)
            ).fetchall()
        return tuple(self._change(row) for row in rows)

    def resolve_conflict(
        self, conflict_id: str, *, resolution: str, payload: dict, resolved_at_utc: str
    ) -> None:
        if resolution not in {"keep_local", "accept_remote", "manual"}:
            raise ValueError("unsupported conflict resolution")
        with self._factory.connect() as connection:
            result = connection.execute(
                "UPDATE sync_conflicts SET resolution=?,resolved_payload_json=?,"
                "resolved_at_utc=? WHERE conflict_id=? AND resolved_at_utc=''",
                (resolution, json.dumps(payload, sort_keys=True), resolved_at_utc, conflict_id),
            )
        if result.rowcount != 1:
            raise ValueError("conflict is missing or already resolved")
