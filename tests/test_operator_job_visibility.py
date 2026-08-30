from __future__ import annotations

from natureai_next.server.jobs import ServerJobStore
from natureai_next.server.linked_storage_operator_api import _operator_job_snapshot
from natureai_next.server.linked_storage_operator_web import (
    _LINKED_STORAGE_OPERATOR_WEB_PATCH,
)


def test_operator_job_snapshot_is_bounded_scoped_and_payload_free(tmp_path) -> None:
    store = ServerJobStore(tmp_path / "jobs.sqlite3")
    visible = store.enqueue(
        "staged.process",
        "subject-secret",
        "org-1",
        "project-1",
        {
            "submission_id": "submission-secret",
            "staged_file_ids": ["file-secret"],
            "credential": "must-not-leak",
        },
    )
    store.enqueue(
        "export_project",
        "other-subject",
        "org-2",
        "other-project",
        {"recipient_public_key": "other-secret"},
    )

    snapshot = _operator_job_snapshot(
        store,
        "org-1",
        {"by_status": {"queued": 1}, "oldest_queued_at_utc": "known"},
    )

    assert snapshot["by_status"] == {"queued": 1}
    assert snapshot["oldest_queued_at_utc"] == "known"
    assert snapshot["recent"] == [
        {
            "job_id": visible.job_id,
            "job_type": "staged.process",
            "project_id": "project-1",
            "status": "queued",
            "attempts": 0,
            "created_at_utc": visible.created_at_utc,
            "updated_at_utc": visible.updated_at_utc,
            "lease_owner": "",
        }
    ]
    serialized = repr(snapshot)
    assert "subject-secret" not in serialized
    assert "submission-secret" not in serialized
    assert "file-secret" not in serialized
    assert "must-not-leak" not in serialized
    assert "other-project" not in serialized


def test_operator_web_renders_jobs_as_rows_not_raw_json() -> None:
    patch = _LINKED_STORAGE_OPERATOR_WEB_PATCH.decode("utf-8")

    assert 'data-operator-job="${html(job.job_id)}"' in patch
    assert 'id="operator-job-summary"' in patch
    assert "renderJobs(overview.jobs||{})" in patch
    assert 'q("operator-jobs").textContent=JSON.stringify' not in patch
