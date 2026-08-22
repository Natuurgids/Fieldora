"""Platform extensions that preserve Library-first evidence ownership."""

from __future__ import annotations

import time
from uuid import uuid4

from natureai_next.server.staged_ingestion import (
    PUBLICATION_POLICIES,
    StagedIngestionStore,
    StagedSubmission,
)


class ProjectOptionalStagedIngestionStore(StagedIngestionStore):
    """Staged intake where project context is optional rather than ownership.

    The underlying reference schema keeps ``project_id`` as a non-null text value for
    compatibility.  The empty string means institution/general-Library intake.
    """

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
