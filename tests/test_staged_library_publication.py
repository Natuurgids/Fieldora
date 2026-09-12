from __future__ import annotations

import hashlib

from natureai_next.server.jobs import ServerJobStore
from natureai_next.server.staged_library_publication import (
    PublishingGovernedMediaStore,
    PublishingProjectOptionalStagedIngestionStore,
    PublishingStagedIngestionService,
)


class _CleanScanner:
    @staticmethod
    def scan(_path):
        return True, "clean"


class _UnavailableScanner:
    @staticmethod
    def scan(_path):
        return False, "scanner_unavailable:FileNotFoundError"


def _service(tmp_path, scanner=None):
    media = PublishingGovernedMediaStore(
        tmp_path / "media.sqlite3",
        tmp_path / "media",
    )
    store = PublishingProjectOptionalStagedIngestionStore(
        tmp_path / "staged.sqlite3",
        tmp_path / "quarantine",
    )
    service = PublishingStagedIngestionService(
        store,
        ServerJobStore(tmp_path / "jobs.sqlite3"),
        malware_scanner=scanner or _CleanScanner(),
    )
    return media, store, service


def _publish(service, store, payload: bytes, *, project_id: str = ""):
    digest = hashlib.sha256(payload).hexdigest()
    submission = store.create_submission(
        subject_id="user-1",
        organization_id="organization-1",
        project_id=project_id,
        contract_id="",
        purpose="research",
        publication_policy="review",
        expected_files=1,
    )
    item = store.begin_file(
        submission.submission_id,
        relative_path="camera/day-1/photo.jpg",
        filename="photo.jpg",
        mime_type="image/jpeg",
        expected_size=len(payload),
        expected_sha256=digest,
    )
    store.append(item.staged_file_id, 0, payload)
    service.seal_and_queue(submission.submission_id)
    validation = service.validate_file(item.staged_file_id)
    assert validation["accepted"] is True
    service.queue_processing(submission.submission_id)
    result = service.process_batch((item.staged_file_id,))
    assert result == {"processed": 1, "published": 1}
    published = store.file(item.staged_file_id)
    assert published is not None
    assert published.state == "published"
    assert published.media_id
    final_submission = store.submission(submission.submission_id)
    assert final_submission is not None
    assert final_submission.state == "published"
    return published


def test_general_library_folder_processing_publishes_governed_media(tmp_path) -> None:
    media, store, service = _service(tmp_path)

    published = _publish(service, store, b"fieldora-folder-photo")

    records = media.records("organization-1")
    assert len(records) == 1
    assert records[0].media_id == published.media_id
    assert records[0].project_id == ""
    assert media.read_range(records[0], 0, records[0].size_bytes - 1) == b"fieldora-folder-photo"
    context = store.pending_contract_context(published.media_id)
    assert context is not None
    assert context.requested_by == "user-1"
    assert context.source_project_id == ""
    assert len(context.targets) == 1
    assert context.targets[0].organization_id == "organization-1"


def test_project_folder_context_is_association_not_evidence_ownership(tmp_path) -> None:
    media, store, service = _service(tmp_path)
    payload = b"same-governed-evidence"

    first = _publish(service, store, payload, project_id="project-1")
    second = _publish(service, store, payload, project_id="project-2")

    assert first.media_id == second.media_id
    records = media.records("organization-1")
    assert len(records) == 1
    assert records[0].project_id == ""
    assert media.associations.linked_media_ids(
        "organization-1", "project", "project-1"
    ) == (first.media_id,)
    assert media.associations.linked_media_ids(
        "organization-1", "project", "project-2"
    ) == (first.media_id,)


def test_all_rejected_folder_is_terminal_instead_of_stuck_ready_to_publish(tmp_path) -> None:
    _media, store, service = _service(tmp_path, _UnavailableScanner())
    payload = b"scanner-failure-must-not-hang"
    digest = hashlib.sha256(payload).hexdigest()
    submission = store.create_submission(
        subject_id="user-1",
        organization_id="organization-1",
        project_id="",
        contract_id="",
        purpose="research",
        publication_policy="review",
        expected_files=1,
    )
    item = store.begin_file(
        submission.submission_id,
        relative_path="folder/photo.jpg",
        filename="photo.jpg",
        mime_type="image/jpeg",
        expected_size=len(payload),
        expected_sha256=digest,
    )
    store.append(item.staged_file_id, 0, payload)
    service.seal_and_queue(submission.submission_id)

    validation = service.validate_file(item.staged_file_id)

    assert validation["accepted"] is False
    assert validation["malware_detail"] == "scanner_unavailable:FileNotFoundError"
    final = store.submission(submission.submission_id)
    assert final is not None
    assert final.state == "rejected"
    assert store.files(submission.submission_id, "validated") == ()


def test_folder_browser_waits_for_published_not_ready_to_publish() -> None:
    from natureai_next.server.api import ApiResponse
    from natureai_next.server.directory_intake_web import patch_directory_intake_response

    response = patch_directory_intake_response(
        "/app.js",
        ApiResponse(200, b"window.base=true;", "text/javascript"),
    )

    assert b'if(submission.state==="published")return current;' in response.body
    assert b'["ready_to_publish","published"].includes(submission.state)' not in response.body
    assert b"Folder imported" in response.body
