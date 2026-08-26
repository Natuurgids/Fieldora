from __future__ import annotations

import hashlib
import sqlite3
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


def _assert_one_managed_instance(store: GovernedMediaStore, record: MediaRecord) -> None:
    instances = store.instances(record.media_id, record.organization_id)
    assert len(instances) == 1
    instance = instances[0]
    assert instance.media_id == record.media_id
    assert instance.organization_id == record.organization_id
    assert instance.storage_kind == "managed"
    assert instance.availability == "available"
    assert instance.size_bytes == record.size_bytes
    assert instance.sha256 == record.sha256


def test_repeated_verified_upload_returns_existing_evidence_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = b"the same governed evidence bytes"

    first = _upload(store, payload)
    repeated = _upload(store, payload, filename="renamed-copy.bin")

    assert repeated.media_id == first.media_id
    assert repeated.relative_path == first.relative_path
    assert repeated.sha256 == first.sha256
    assert store.records("organization-1", "project-1") == (first,)
    _assert_one_managed_instance(store, first)


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
    _assert_one_managed_instance(store, first)


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
    _assert_one_managed_instance(store, first)


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
    _assert_one_managed_instance(store, records[0])


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
    _assert_one_managed_instance(store, records[0])


def test_existing_sqlite_governed_media_is_backfilled_as_managed(tmp_path: Path) -> None:
    database = tmp_path / "media.sqlite3"
    media_id = "legacy-media"
    payload = b"legacy managed bytes"
    digest = hashlib.sha256(payload).hexdigest()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE governed_media("
            "media_id TEXT PRIMARY KEY,relative_path TEXT NOT NULL UNIQUE,"
            "organization_id TEXT NOT NULL,project_id TEXT NOT NULL,"
            "mime_type TEXT NOT NULL,size_bytes INTEGER NOT NULL,sha256 TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO governed_media VALUES(?,?,?,?,?,?,?)",
            (
                media_id,
                "legacy/object.bin",
                "organization-1",
                "project-1",
                "application/octet-stream",
                len(payload),
                digest,
            ),
        )

    store = GovernedMediaStore(database, tmp_path / "objects")
    record = store.record(media_id)

    assert record is not None
    _assert_one_managed_instance(store, record)


def test_referenced_content_has_canonical_identity_without_managed_object(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = b"referenced-only evidence"
    digest = hashlib.sha256(payload).hexdigest()
    source_ref = f"linked:storage-1:object-1:{digest}"

    first = store.attach_referenced(
        organization_id="organization-1",
        project_id="project-1",
        mime_type="application/octet-stream",
        size_bytes=len(payload),
        sha256=digest,
        source_ref=source_ref,
    )
    repeated = store.attach_referenced(
        organization_id="organization-1",
        project_id="project-1",
        mime_type="application/octet-stream",
        size_bytes=len(payload),
        sha256=digest,
        source_ref=source_ref,
    )

    assert repeated.media_id == first.media_id
    assert first.relative_path is None
    assert len(store.records("organization-1")) == 1
    assert _object_files(tmp_path) == []
    instances = store.instances(first.media_id, "organization-1")
    assert len(instances) == 1
    assert instances[0].storage_kind == "referenced"
    assert instances[0].availability == "available"
    assert instances[0].source_ref == source_ref


def test_referenced_then_managed_bytes_upgrade_same_canonical_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = b"referenced evidence later managed"
    digest = hashlib.sha256(payload).hexdigest()
    referenced = store.attach_referenced(
        organization_id="organization-1",
        project_id="project-1",
        mime_type="application/octet-stream",
        size_bytes=len(payload),
        sha256=digest,
        source_ref=f"linked:storage-1:object-2:{digest}",
    )
    source = tmp_path / "later-managed.bin"
    source.write_bytes(payload)

    managed = store.register(source, "organization-1", "project-1")

    assert managed.media_id == referenced.media_id
    assert managed.relative_path is not None
    assert len(store.records("organization-1")) == 1
    assert len(_object_files(tmp_path)) == 1
    instances = store.instances(managed.media_id, "organization-1")
    assert [instance.storage_kind for instance in instances] == ["managed", "referenced"]


def test_managed_then_referenced_bytes_keep_same_canonical_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = b"managed evidence later referenced"
    managed = _upload(store, payload)
    referenced = store.attach_referenced(
        organization_id="organization-1",
        project_id="project-1",
        mime_type=managed.mime_type,
        size_bytes=managed.size_bytes,
        sha256=managed.sha256,
        source_ref=f"linked:storage-2:object-1:{managed.sha256}",
    )

    assert referenced.media_id == managed.media_id
    assert referenced.relative_path == managed.relative_path
    assert len(store.records("organization-1")) == 1
    instances = store.instances(managed.media_id, "organization-1")
    assert [instance.storage_kind for instance in instances] == ["managed", "referenced"]
