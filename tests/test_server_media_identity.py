from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from natureai_next.server.media import GovernedMediaStore, MediaRecord, UploadSession


def _store(tmp_path: Path) -> GovernedMediaStore:
    return GovernedMediaStore(
        tmp_path / "media.sqlite3",
        tmp_path / "objects",
    )


def _upload(
    store: GovernedMediaStore,
    payload: bytes,
    *,
    project_id: str = "project-1",
    filename: str = "evidence.bin",
) -> MediaRecord:
    digest = hashlib.sha256(payload).hexdigest()
    upload = store.begin_upload(
        "subject-1",
        "organization-1",
        project_id,
        filename,
        "application/octet-stream",
        len(payload),
        digest,
    )
    result = store.append_upload(upload, 0, payload)
    assert isinstance(result, MediaRecord)
    return result


def _object_files(tmp_path: Path) -> list[Path]:
    return [
        path
        for path in (tmp_path / "objects").rglob("*")
        if path.is_file() and ".uploads" not in path.parts
    ]


def test_repeated_verified_upload_returns_existing_evidence_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = b"the same governed evidence bytes"

    first = _upload(store, payload)
    repeated = _upload(store, payload, filename="renamed-copy.bin")

    assert repeated.media_id == first.media_id
    assert repeated.relative_path == first.relative_path
    assert repeated.sha256 == first.sha256
    assert store.records("organization-1", "project-1") == (first,)


def test_registering_same_bytes_twice_is_idempotent_in_same_context(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first_source = tmp_path / "first.txt"
    repeated_source = tmp_path / "renamed.txt"
    first_source.write_bytes(b"identical evidence")
    repeated_source.write_bytes(first_source.read_bytes())

    first = store.register(first_source, "organization-1", "project-1")
    repeated = store.register(repeated_source, "organization-1", "project-1")

    assert repeated.media_id == first.media_id
    assert store.records("organization-1", "project-1") == (first,)


def test_same_bytes_in_another_project_use_one_organization_evidence_identity(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    payload = b"shared evidence bytes"

    first = _upload(store, payload, project_id="project-1")
    second = _upload(store, payload, project_id="project-2")

    assert second.media_id == first.media_id
    assert second.relative_path == first.relative_path
    assert len(store.records("organization-1")) == 1


def test_concurrent_verified_uploads_converge_to_one_sqlite_evidence_identity(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    payload = b"concurrent canonical evidence bytes"
    digest = hashlib.sha256(payload).hexdigest()
    uploads: list[UploadSession] = []
    for index in range(8):
        uploads.append(
            store.begin_upload(
                f"subject-{index}",
                "organization-1",
                "project-1",
                f"evidence-{index}.bin",
                "application/octet-stream",
                len(payload),
                digest,
            )
        )

    barrier = threading.Barrier(len(uploads))

    def complete(upload: UploadSession) -> MediaRecord:
        barrier.wait(timeout=10)
        result = store.append_upload(upload, 0, payload)
        assert isinstance(result, MediaRecord)
        return result

    with ThreadPoolExecutor(max_workers=len(uploads)) as executor:
        records = list(executor.map(complete, uploads))

    assert len({record.media_id for record in records}) == 1
    assert len(store.records("organization-1")) == 1
    assert len(_object_files(tmp_path)) == 1


def test_concurrent_registers_converge_to_one_sqlite_evidence_identity(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    payload = b"concurrent direct registration bytes"
    sources: list[Path] = []
    for index in range(8):
        source = tmp_path / f"source-{index}.bin"
        source.write_bytes(payload)
        sources.append(source)

    barrier = threading.Barrier(len(sources))

    def register(source: Path) -> MediaRecord:
        barrier.wait(timeout=10)
        return store.register(source, "organization-1", "project-1")

    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        records = list(executor.map(register, sources))

    assert len({record.media_id for record in records}) == 1
    assert len(store.records("organization-1")) == 1
    assert len(_object_files(tmp_path)) == 1
