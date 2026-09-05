"""Platform extensions that preserve Library-first evidence ownership."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from uuid import uuid4

from natureai_next.server.access_contracts import AccessTarget, AccessTargetKind, ContractDraft
from natureai_next.server.staged_ingestion import (
    PUBLICATION_POLICIES,
    StagedIngestionStore,
    StagedSubmission,
)


@dataclass(frozen=True, slots=True)
class StagedAccessContext:
    submission_id: str
    requested_by: str
    source_project_id: str
    inherited_contract_id: str
    targets: tuple[AccessTarget, ...]
    recorded_at_epoch: int

    def draft(self) -> ContractDraft:
        return ContractDraft(
            self.targets,
            self.inherited_contract_id,
            False,
            0,
            source_project_id=self.source_project_id,
        )


class ProjectOptionalStagedIngestionStore(StagedIngestionStore):
    """Staged intake where project context is optional rather than ownership.

    Contract scope is snapshotted when authenticated intake begins. Publication records
    a pending contract binding so workers cannot silently turn staged evidence into a
    PBAC-only asset if access-contract persistence is temporarily unavailable.
    """

    def __init__(self, database_path, quarantine_root) -> None:
        super().__init__(database_path, quarantine_root)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS staged_access_contexts(
                    submission_id TEXT PRIMARY KEY REFERENCES staged_submissions(submission_id),
                    requested_by TEXT NOT NULL,
                    source_project_id TEXT NOT NULL,
                    inherited_contract_id TEXT NOT NULL,
                    targets_json TEXT NOT NULL,
                    recorded_at_epoch INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS staged_pending_contract_bindings(
                    media_id TEXT PRIMARY KEY,
                    submission_id TEXT NOT NULL REFERENCES staged_submissions(submission_id),
                    staged_file_id TEXT NOT NULL,
                    created_at_epoch INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_staged_pending_contract_submission
                    ON staged_pending_contract_bindings(submission_id,media_id);
                """
            )

    def create_submission(
        self,
        *,
        subject_id: str,
        organization_id: str,
        project_id: str = "",
        contract_id: str = "",
        purpose: str,
        publication_policy: str,
        expected_files: int,
    ) -> StagedSubmission:
        if publication_policy not in PUBLICATION_POLICIES:
            raise ValueError("invalid publication policy")
        if not 1 <= expected_files <= 1_000_000:
            raise ValueError("expected_files must be between 1 and 1000000")
        if not all(value.strip() for value in (subject_id, organization_id, purpose)):
            raise ValueError("submission contributor, organization, and purpose are required")
        now = int(time.time())
        submission_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO staged_submissions VALUES(?,?,?,?,?,?,?,?,?,0,0,?,?)",
                (
                    submission_id,
                    subject_id.strip(),
                    organization_id.strip(),
                    project_id.strip(),
                    contract_id.strip(),
                    purpose.strip(),
                    publication_policy,
                    "uploading",
                    expected_files,
                    now,
                    now,
                ),
            )
            self._event(
                connection,
                submission_id,
                "",
                "submission_created",
                {"scope": "project" if project_id.strip() else "library"},
            )
        result = self.submission(submission_id)
        assert result is not None
        return result

    def record_access_context(
        self,
        submission_id: str,
        *,
        requested_by: str,
        draft: ContractDraft,
        now_epoch: int | None = None,
    ) -> StagedAccessContext:
        if not requested_by.strip() or not draft.targets:
            raise ValueError("staged access context requires actor and resolved targets")
        if self.submission(submission_id) is None:
            raise KeyError(submission_id)
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        payload = json.dumps(
            [
                {
                    "kind": target.kind.value,
                    "organization_id": target.organization_id,
                    "project_id": target.project_id,
                }
                for target in draft.targets
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO staged_access_contexts VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(submission_id) DO UPDATE SET "
                "requested_by=excluded.requested_by,"
                "source_project_id=excluded.source_project_id,"
                "inherited_contract_id=excluded.inherited_contract_id,"
                "targets_json=excluded.targets_json,"
                "recorded_at_epoch=excluded.recorded_at_epoch",
                (
                    submission_id,
                    requested_by.strip(),
                    draft.source_project_id,
                    draft.inherited_contract_id,
                    payload,
                    now,
                ),
            )
        result = self.access_context(submission_id)
        assert result is not None
        return result

    def access_context(self, submission_id: str) -> StagedAccessContext | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT submission_id,requested_by,source_project_id,inherited_contract_id,"
                "targets_json,recorded_at_epoch FROM staged_access_contexts "
                "WHERE submission_id=?",
                (submission_id,),
            ).fetchone()
        if row is None:
            return None
        raw = json.loads(str(row[4]))
        targets = tuple(
            AccessTarget(
                AccessTargetKind(str(item["kind"])),
                organization_id=str(item.get("organization_id", "")),
                project_id=str(item.get("project_id", "")),
            )
            for item in raw
        )
        return StagedAccessContext(
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            targets,
            int(row[5]),
        )

    def mark_published(self, staged_file_id: str, media_id: str) -> None:
        """Record publication and require a later authoritative access binding."""
        super().mark_published(staged_file_id, media_id)
        item = self.file(staged_file_id)
        if item is None or item.state != "published" or item.media_id != media_id:
            raise ValueError("staged file was not published")
        if self.access_context(item.submission_id) is None:
            raise ValueError("staged submission has no durable access context")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO staged_pending_contract_bindings VALUES(?,?,?,?) "
                "ON CONFLICT(media_id) DO NOTHING",
                (media_id, item.submission_id, staged_file_id, int(time.time())),
            )

    def pending_contract_context(self, media_id: str) -> StagedAccessContext | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT submission_id FROM staged_pending_contract_bindings WHERE media_id=?",
                (media_id,),
            ).fetchone()
        return None if row is None else self.access_context(str(row[0]))

    def complete_contract_binding(self, media_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM staged_pending_contract_bindings WHERE media_id=?",
                (media_id,),
            )

    def pending_contract_media_ids(self, limit: int = 1000) -> tuple[str, ...]:
        bounded = max(1, min(int(limit), 10_000))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT media_id FROM staged_pending_contract_bindings "
                "ORDER BY created_at_epoch,media_id LIMIT ?",
                (bounded,),
            ).fetchall()
        return tuple(str(row[0]) for row in rows)
