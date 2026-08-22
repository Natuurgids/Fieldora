from __future__ import annotations

import hashlib
from pathlib import Path

from natureai_next.server.jobs import ServerJobStore, run_one_job
from natureai_next.server.search import ServerSearchProjection
from natureai_next.server.staged_ingestion import (
    StagedIngestionService,
    StagedIngestionStore,
)


class _CleanScanner:
    def scan(self, _path: Path) -> tuple[bool, str]:
        return True, "clean:test"


class _RejectScanner:
    def scan(self, _path: Path) -> tuple[bool, str]:
        return False, "malware:test-signature"


def _service(tmp_path: Path, scanner=None, batch_size: int = 2):
    jobs = ServerJobStore(tmp_path / "jobs.sqlite3")
    store = StagedIngestionStore(
        tmp_path / "staging.sqlite3", tmp_path / "quarantine"
    )
    service = StagedIngestionService(
        store,
        jobs,
        malware_scanner=scanner or _CleanScanner(),
        import_batch_size=batch_size,
    )
    return service, jobs


def _upload(service: StagedIngestionService, submission_id: str, name: str, data: bytes):
    item = service.store.begin_file(
        submission_id,
        relative_path=f"field/day-1/{name}",
        filename=name,
        mime_type="application/octet-stream",
        expected_size=len(data),
        expected_sha256=hashlib.sha256(data).hexdigest(),
    )
    midpoint = max(1, len(data) // 2)
    service.store.append(item.staged_file_id, 0, data[:midpoint])
    return service.store.append(item.staged_file_id, midpoint, data[midpoint:])


def test_quarantine_validation_and_bounded_processing_jobs(tmp_path: Path) -> None:
    service, jobs = _service(tmp_path, batch_size=2)
    submission = service.store.create_submission(
        subject_id="user-1",
        organization_id="org-1",
        project_id="project-1",
        contract_id="contract-1",
        purpose="research",
        publication_policy="review",
        expected_files=3,
    )
    uploaded = tuple(
        _upload(service, submission.submission_id, f"photo-{index}.jpg", payload)
        for index, payload in enumerate((b"one", b"two", b"three"), 1)
    )

    sealed = service.seal_and_queue(submission.submission_id)
    assert sealed.state == "scanning"
    assert all(item.state == "uploaded" for item in uploaded)

    search = ServerSearchProjection(tmp_path / "search.sqlite3")
    for _ in range(3):
        completed = run_one_job(
            jobs,
            search,
            tmp_path / "science.sqlite3",
            staged_ingestion=service,
        )
        assert completed is not None and completed.status == "succeeded"

    queued = [
        job
        for job in (
            jobs.claim(worker_id="inspection-1"),
            jobs.claim(worker_id="inspection-2"),
        )
        if job is not None
    ]
    assert [job.job_type for job in queued] == ["staged.process", "staged.process"]
    assert sorted(len(job.payload["staged_file_ids"]) for job in queued) == [1, 2]
    assert all(job.payload["contract_id"] == "contract-1" for job in queued)
    assert all(job.payload["purpose"] == "research" for job in queued)


def test_malware_rejection_never_enters_processing(tmp_path: Path) -> None:
    service, jobs = _service(tmp_path, scanner=_RejectScanner())
    submission = service.store.create_submission(
        subject_id="user-1",
        organization_id="org-1",
        project_id="project-1",
        contract_id="",
        purpose="research",
        publication_policy="review",
        expected_files=1,
    )
    item = _upload(service, submission.submission_id, "sample.bin", b"unsafe")
    service.seal_and_queue(submission.submission_id)
    completed = run_one_job(
        jobs,
        ServerSearchProjection(tmp_path / "search.sqlite3"),
        tmp_path / "science.sqlite3",
        staged_ingestion=service,
    )

    assert completed is not None and completed.status == "succeeded"
    rejected = service.store.file(item.staged_file_id)
    assert rejected is not None and rejected.state == "rejected"
    assert rejected.validation_json["malware_clean"] is False
    assert jobs.claim(worker_id="nothing-to-process") is None


def test_checksum_mismatch_is_rejected_before_malware_result_can_publish(
    tmp_path: Path,
) -> None:
    service, _jobs = _service(tmp_path)
    submission = service.store.create_submission(
        subject_id="user-1",
        organization_id="org-1",
        project_id="project-1",
        contract_id="",
        purpose="research",
        publication_policy="atomic",
        expected_files=1,
    )
    item = service.store.begin_file(
        submission.submission_id,
        relative_path="changed.jpg",
        filename="changed.jpg",
        mime_type="image/jpeg",
        expected_size=4,
        expected_sha256=hashlib.sha256(b"good").hexdigest(),
    )
    service.store.append(item.staged_file_id, 0, b"evil")
    service.store.seal(submission.submission_id)
    result = service.validate_file(item.staged_file_id)

    assert result["accepted"] is False
    assert result["checksum_valid"] is False
    assert service.store.file(item.staged_file_id).state == "rejected"


def test_staging_rejects_path_traversal_and_incomplete_seal(tmp_path: Path) -> None:
    service, _jobs = _service(tmp_path)
    submission = service.store.create_submission(
        subject_id="user-1",
        organization_id="org-1",
        project_id="project-1",
        contract_id="",
        purpose="research",
        publication_policy="progressive",
        expected_files=1,
    )
    try:
        service.store.begin_file(
            submission.submission_id,
            relative_path="../escape.jpg",
            filename="escape.jpg",
            mime_type="image/jpeg",
            expected_size=1,
            expected_sha256=hashlib.sha256(b"x").hexdigest(),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal was accepted")
    try:
        service.store.seal(submission.submission_id)
    except ValueError:
        pass
    else:
        raise AssertionError("incomplete submission was sealed")
