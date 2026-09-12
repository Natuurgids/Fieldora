"""Durable offline synchronization exchange store.

This repository is intentionally exchange-facing: desktop/mobile nodes submit bundles
through a governed API boundary. Competing assertions are retained side-by-side and a
separate append-only resolution history controls presentation.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from natureai_next.domain.synchronization import (
    AssertionState,
    PrimaryResolution,
    SyncApplyResult,
    SyncAssertion,
    SyncBundle,
    SyncBundleState,
    assertions_disagree,
)


class OfflineSyncStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_bundles(
                    bundle_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    source_device_id TEXT NOT NULL,
                    source_identity_id TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    state TEXT NOT NULL,
                    checkpoint TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_assertions(
                    assertion_id TEXT PRIMARY KEY,
                    logical_record_id TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    author_identity_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    source_bundle_id TEXT NOT NULL,
                    contract_id TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    parent_assertion_id TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_sync_assertions_logical "
                "ON sync_assertions(organization_id,record_type,logical_record_id,created_at_utc)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_resolutions(
                    resolution_id TEXT PRIMARY KEY,
                    logical_record_id TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    primary_assertion_id TEXT NOT NULL,
                    decided_by_identity_id TEXT NOT NULL,
                    decided_at_utc TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    audience TEXT NOT NULL,
                    previous_resolution_id TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_sync_resolutions_current "
                "ON sync_resolutions(organization_id,record_type,logical_record_id,audience,decided_at_utc)"
            )

    def apply_bundle(self, bundle: SyncBundle) -> SyncApplyResult:
        """Persist a bundle idempotently without overwriting discrepant assertions."""

        inserted: list[str] = []
        duplicates: list[str] = []
        conflicts: set[str] = set()
        rejected: list[str] = []
        with sqlite3.connect(self._database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing_bundle = connection.execute(
                "SELECT bundle_id FROM sync_bundles WHERE bundle_id=?", (bundle.bundle_id,)
            ).fetchone()
            if existing_bundle is not None:
                return self._result_for_existing_bundle(connection, bundle.bundle_id)

            connection.execute(
                "INSERT INTO sync_bundles VALUES(?,?,?,?,?,?,?,?)",
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
                if assertion.source_bundle_id and assertion.source_bundle_id != bundle.bundle_id:
                    rejected.append(assertion.assertion_id)
                    continue
                existing = connection.execute(
                    "SELECT assertion_id FROM sync_assertions WHERE assertion_id=?",
                    (assertion.assertion_id,),
                ).fetchone()
                if existing is not None:
                    duplicates.append(assertion.assertion_id)
                    continue

                peers = tuple(
                    self._decode_assertion(row)
                    for row in connection.execute(
                        "SELECT * FROM sync_assertions WHERE organization_id=? "
                        "AND record_type=? AND logical_record_id=?",
                        (
                            assertion.organization_id,
                            assertion.record_type,
                            assertion.logical_record_id,
                        ),
                    ).fetchall()
                )
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
                self._insert_assertion(connection, stored)
                inserted.append(stored.assertion_id)

            final_state = (
                SyncBundleState.PARTIAL
                if rejected
                else SyncBundleState.APPLIED
            )
            connection.execute(
                "UPDATE sync_bundles SET state=? WHERE bundle_id=?",
                (final_state.value, bundle.bundle_id),
            )
            connection.commit()

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
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM sync_assertions WHERE organization_id=? "
                "AND record_type=? AND logical_record_id=? ORDER BY created_at_utc,assertion_id",
                (organization_id, record_type, logical_record_id),
            ).fetchall()
        return tuple(self._decode_assertion(row) for row in rows)

    def resolve_primary(self, resolution: PrimaryResolution) -> None:
        """Append a presentation decision; never delete or rewrite an assertion."""

        with sqlite3.connect(self._database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT assertion_id FROM sync_assertions WHERE assertion_id=? "
                "AND organization_id=? AND record_type=? AND logical_record_id=?",
                (
                    resolution.primary_assertion_id,
                    resolution.organization_id,
                    resolution.record_type,
                    resolution.logical_record_id,
                ),
            ).fetchone()
            if row is None:
                raise ValueError("primary assertion is not part of the logical record")
            latest = connection.execute(
                "SELECT resolution_id FROM sync_resolutions WHERE organization_id=? "
                "AND record_type=? AND logical_record_id=? AND audience=? "
                "ORDER BY decided_at_utc DESC,resolution_id DESC LIMIT 1",
                (
                    resolution.organization_id,
                    resolution.record_type,
                    resolution.logical_record_id,
                    resolution.audience,
                ),
            ).fetchone()
            expected_previous = "" if latest is None else str(latest[0])
            if resolution.previous_resolution_id != expected_previous:
                raise ValueError("resolution history conflict")
            connection.execute(
                "INSERT INTO sync_resolutions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
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
            connection.commit()

    def current_resolution(
        self,
        organization_id: str,
        record_type: str,
        logical_record_id: str,
        audience: str = "organization",
    ) -> PrimaryResolution | None:
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT * FROM sync_resolutions WHERE organization_id=? "
                "AND record_type=? AND logical_record_id=? AND audience=? "
                "ORDER BY decided_at_utc DESC,resolution_id DESC LIMIT 1",
                (organization_id, record_type, logical_record_id, audience),
            ).fetchone()
        return None if row is None else PrimaryResolution(*row)

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
        self, connection: sqlite3.Connection, bundle_id: str
    ) -> SyncApplyResult:
        rows = connection.execute(
            "SELECT assertion_id,logical_record_id,state FROM sync_assertions "
            "WHERE source_bundle_id=? ORDER BY assertion_id",
            (bundle_id,),
        ).fetchall()
        ids = tuple(str(row[0]) for row in rows)
        conflicts = tuple(sorted({str(row[1]) for row in rows if row[2] == AssertionState.DISPUTED.value}))
        return SyncApplyResult(bundle_id, (), ids, conflicts, ())

    @staticmethod
    def _insert_assertion(
        connection: sqlite3.Connection, assertion: SyncAssertion
    ) -> None:
        connection.execute(
            "INSERT INTO sync_assertions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
    def _decode_assertion(row: tuple[object, ...]) -> SyncAssertion:
        return SyncAssertion(
            assertion_id=str(row[0]),
            logical_record_id=str(row[1]),
            record_type=str(row[2]),
            organization_id=str(row[3]),
            project_id=str(row[4]),
            author_identity_id=str(row[5]),
            device_id=str(row[6]),
            created_at_utc=str(row[7]),
            payload=dict(json.loads(str(row[8]))),
            state=AssertionState(str(row[9])),
            source_bundle_id=str(row[10]),
            contract_id=str(row[11]),
            evidence_ids=tuple(str(item) for item in json.loads(str(row[12]))),
            parent_assertion_id=str(row[13]),
        )
