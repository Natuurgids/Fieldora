"""PostgreSQL repository for offline-first synchronization exchange state."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from natureai_next.domain.synchronization import (
    AssertionState,
    PrimaryResolution,
    SyncApplyResult,
    SyncAssertion,
    SyncBundle,
    SyncBundleState,
    assertions_disagree,
)


class PostgresOfflineSyncStore:
    """Multi-server safe exchange repository using one shared PostgreSQL database."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("fieldora_offline_sync_schema_v1",),
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sync_bundles(
                        bundle_id TEXT PRIMARY KEY,
                        organization_id TEXT NOT NULL,
                        source_device_id TEXT NOT NULL,
                        source_identity_id TEXT NOT NULL,
                        created_at_utc TIMESTAMPTZ NOT NULL,
                        state TEXT NOT NULL,
                        checkpoint TEXT NOT NULL,
                        metadata_json JSONB NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sync_assertions(
                        assertion_id TEXT PRIMARY KEY,
                        logical_record_id TEXT NOT NULL,
                        record_type TEXT NOT NULL,
                        organization_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        author_identity_id TEXT NOT NULL,
                        device_id TEXT NOT NULL,
                        created_at_utc TIMESTAMPTZ NOT NULL,
                        payload_json JSONB NOT NULL,
                        state TEXT NOT NULL,
                        source_bundle_id TEXT NOT NULL REFERENCES sync_bundles(bundle_id),
                        contract_id TEXT NOT NULL,
                        evidence_ids_json JSONB NOT NULL,
                        parent_assertion_id TEXT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_sync_assertions_logical_pg "
                    "ON sync_assertions(organization_id,record_type,logical_record_id,created_at_utc,assertion_id)"
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sync_resolutions(
                        resolution_id TEXT PRIMARY KEY,
                        logical_record_id TEXT NOT NULL,
                        record_type TEXT NOT NULL,
                        organization_id TEXT NOT NULL,
                        project_id TEXT NOT NULL,
                        primary_assertion_id TEXT NOT NULL REFERENCES sync_assertions(assertion_id),
                        decided_by_identity_id TEXT NOT NULL,
                        decided_at_utc TIMESTAMPTZ NOT NULL,
                        rationale TEXT NOT NULL,
                        audience TEXT NOT NULL,
                        previous_resolution_id TEXT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_sync_resolutions_current_pg "
                    "ON sync_resolutions(organization_id,record_type,logical_record_id,audience,decided_at_utc,resolution_id)"
                )

    def apply_bundle(self, bundle: SyncBundle) -> SyncApplyResult:
        inserted: list[str] = []
        duplicates: list[str] = []
        conflicts: set[str] = set()
        rejected: list[str] = []
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT state FROM sync_bundles WHERE bundle_id=%s FOR UPDATE",
                    (bundle.bundle_id,),
                )
                if cursor.fetchone() is not None:
                    return self._result_for_existing_bundle(cursor, bundle.bundle_id)

                cursor.execute(
                    "INSERT INTO sync_bundles("
                    "bundle_id,organization_id,source_device_id,source_identity_id,"
                    "created_at_utc,state,checkpoint,metadata_json"
                    ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                    (
                        bundle.bundle_id,
                        bundle.organization_id,
                        bundle.source_device_id,
                        bundle.source_identity_id,
                        bundle.created_at_utc,
                        SyncBundleState.RECEIVED.value,
                        bundle.checkpoint,
                        json.dumps(bundle.metadata, sort_keys=True),
                    ),
                )

                for assertion in bundle.assertions:
                    if assertion.organization_id != bundle.organization_id:
                        rejected.append(assertion.assertion_id)
                        continue
                    if (
                        assertion.source_bundle_id
                        and assertion.source_bundle_id != bundle.bundle_id
                    ):
                        rejected.append(assertion.assertion_id)
                        continue
                    cursor.execute(
                        "SELECT assertion_id FROM sync_assertions WHERE assertion_id=%s",
                        (assertion.assertion_id,),
                    )
                    if cursor.fetchone() is not None:
                        duplicates.append(assertion.assertion_id)
                        continue

                    cursor.execute(
                        "SELECT assertion_id,logical_record_id,record_type,organization_id,"
                        "project_id,author_identity_id,device_id,created_at_utc,payload_json,"
                        "state,source_bundle_id,contract_id,evidence_ids_json,parent_assertion_id "
                        "FROM sync_assertions WHERE organization_id=%s AND record_type=%s "
                        "AND logical_record_id=%s FOR SHARE",
                        (
                            assertion.organization_id,
                            assertion.record_type,
                            assertion.logical_record_id,
                        ),
                    )
                    peers = tuple(self._decode_assertion(row) for row in cursor.fetchall())
                    if any(assertions_disagree(peer, assertion) for peer in peers):
                        conflicts.add(assertion.logical_record_id)
                        state = AssertionState.DISPUTED
                    elif peers:
                        state = AssertionState.ALTERNATIVE
                    else:
                        state = AssertionState.CURRENT
                    stored = replace(
                        assertion,
                        state=state,
                        source_bundle_id=bundle.bundle_id,
                    )
                    self._insert_assertion(cursor, stored)
                    inserted.append(stored.assertion_id)

                final_state = (
                    SyncBundleState.PARTIAL if rejected else SyncBundleState.APPLIED
                )
                cursor.execute(
                    "UPDATE sync_bundles SET state=%s WHERE bundle_id=%s",
                    (final_state.value, bundle.bundle_id),
                )

        return SyncApplyResult(
            bundle.bundle_id,
            tuple(inserted),
            tuple(duplicates),
            tuple(sorted(conflicts)),
            tuple(rejected),
        )

    def assertions(
        self, organization_id: str, record_type: str, logical_record_id: str
    ) -> tuple[SyncAssertion, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT assertion_id,logical_record_id,record_type,organization_id,"
                    "project_id,author_identity_id,device_id,created_at_utc,payload_json,"
                    "state,source_bundle_id,contract_id,evidence_ids_json,parent_assertion_id "
                    "FROM sync_assertions WHERE organization_id=%s AND record_type=%s "
                    "AND logical_record_id=%s ORDER BY created_at_utc,assertion_id",
                    (organization_id, record_type, logical_record_id),
                )
                rows = cursor.fetchall()
        return tuple(self._decode_assertion(row) for row in rows)

    def resolve_primary(self, resolution: PrimaryResolution) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT assertion_id FROM sync_assertions WHERE assertion_id=%s "
                    "AND organization_id=%s AND record_type=%s AND logical_record_id=%s",
                    (
                        resolution.primary_assertion_id,
                        resolution.organization_id,
                        resolution.record_type,
                        resolution.logical_record_id,
                    ),
                )
                if cursor.fetchone() is None:
                    raise ValueError("primary assertion is not part of the logical record")
                cursor.execute(
                    "SELECT resolution_id FROM sync_resolutions WHERE organization_id=%s "
                    "AND record_type=%s AND logical_record_id=%s AND audience=%s "
                    "ORDER BY decided_at_utc DESC,resolution_id DESC LIMIT 1 FOR UPDATE",
                    (
                        resolution.organization_id,
                        resolution.record_type,
                        resolution.logical_record_id,
                        resolution.audience,
                    ),
                )
                row = cursor.fetchone()
                expected_previous = "" if row is None else str(row[0])
                if resolution.previous_resolution_id != expected_previous:
                    raise ValueError("resolution history conflict")
                cursor.execute(
                    "INSERT INTO sync_resolutions("
                    "resolution_id,logical_record_id,record_type,organization_id,project_id,"
                    "primary_assertion_id,decided_by_identity_id,decided_at_utc,rationale,"
                    "audience,previous_resolution_id"
                    ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        resolution.resolution_id,
                        resolution.logical_record_id,
                        resolution.record_type,
                        resolution.organization_id,
                        resolution.project_id,
                        resolution.primary_assertion_id,
                        resolution.decided_by_identity_id,
                        resolution.decided_at_utc,
                        resolution.rationale,
                        resolution.audience,
                        resolution.previous_resolution_id,
                    ),
                )

    def current_resolution(
        self,
        organization_id: str,
        record_type: str,
        logical_record_id: str,
        audience: str = "organization",
    ) -> PrimaryResolution | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT resolution_id,logical_record_id,record_type,organization_id,"
                    "project_id,primary_assertion_id,decided_by_identity_id,decided_at_utc,"
                    "rationale,audience,previous_resolution_id FROM sync_resolutions "
                    "WHERE organization_id=%s AND record_type=%s AND logical_record_id=%s "
                    "AND audience=%s ORDER BY decided_at_utc DESC,resolution_id DESC LIMIT 1",
                    (organization_id, record_type, logical_record_id, audience),
                )
                row = cursor.fetchone()
        return None if row is None else self._decode_resolution(row)

    def presentation_assertion(
        self,
        organization_id: str,
        record_type: str,
        logical_record_id: str,
        audience: str = "organization",
    ) -> SyncAssertion | None:
        resolution = self.current_resolution(
            organization_id, record_type, logical_record_id, audience
        )
        candidates = self.assertions(organization_id, record_type, logical_record_id)
        if resolution is not None:
            return next(
                (
                    assertion
                    for assertion in candidates
                    if assertion.assertion_id == resolution.primary_assertion_id
                ),
                None,
            )
        return candidates[0] if len(candidates) == 1 else None

    def _result_for_existing_bundle(
        self, cursor: Any, bundle_id: str
    ) -> SyncApplyResult:
        cursor.execute(
            "SELECT assertion_id,logical_record_id,state FROM sync_assertions "
            "WHERE source_bundle_id=%s ORDER BY assertion_id",
            (bundle_id,),
        )
        rows = cursor.fetchall()
        ids = tuple(str(row[0]) for row in rows)
        conflicts = tuple(
            sorted(
                {
                    str(row[1])
                    for row in rows
                    if str(row[2]) == AssertionState.DISPUTED.value
                }
            )
        )
        return SyncApplyResult(bundle_id, (), ids, conflicts, ())

    @staticmethod
    def _insert_assertion(cursor: Any, assertion: SyncAssertion) -> None:
        cursor.execute(
            "INSERT INTO sync_assertions("
            "assertion_id,logical_record_id,record_type,organization_id,project_id,"
            "author_identity_id,device_id,created_at_utc,payload_json,state,source_bundle_id,"
            "contract_id,evidence_ids_json,parent_assertion_id"
            ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s)",
            (
                assertion.assertion_id,
                assertion.logical_record_id,
                assertion.record_type,
                assertion.organization_id,
                assertion.project_id,
                assertion.author_identity_id,
                assertion.device_id,
                assertion.created_at_utc,
                json.dumps(assertion.payload, sort_keys=True),
                assertion.state.value,
                assertion.source_bundle_id,
                assertion.contract_id,
                json.dumps(assertion.evidence_ids),
                assertion.parent_assertion_id,
            ),
        )

    @staticmethod
    def _decode_assertion(row: Any) -> SyncAssertion:
        payload = row[8] if isinstance(row[8], dict) else json.loads(str(row[8]))
        evidence = row[12] if isinstance(row[12], list) else json.loads(str(row[12]))
        created = row[7].isoformat() if hasattr(row[7], "isoformat") else str(row[7])
        return SyncAssertion(
            assertion_id=str(row[0]),
            logical_record_id=str(row[1]),
            record_type=str(row[2]),
            organization_id=str(row[3]),
            project_id=str(row[4]),
            author_identity_id=str(row[5]),
            device_id=str(row[6]),
            created_at_utc=created,
            payload=dict(payload),
            state=AssertionState(str(row[9])),
            source_bundle_id=str(row[10]),
            contract_id=str(row[11]),
            evidence_ids=tuple(str(item) for item in evidence),
            parent_assertion_id=str(row[13]),
        )

    @staticmethod
    def _decode_resolution(row: Any) -> PrimaryResolution:
        decided = row[7].isoformat() if hasattr(row[7], "isoformat") else str(row[7])
        return PrimaryResolution(
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5]),
            str(row[6]),
            decided,
            str(row[8]),
            str(row[9]),
            str(row[10]),
        )
