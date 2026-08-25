from __future__ import annotations

import hashlib
from pathlib import Path

from natureai_next.server.media import GovernedMediaStore, MediaRecord


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


def test_same_bytes_in_another_project_remain_separate_until_association_slice(
    tmp_path: Path,
) -> None:
    """WEB-011 will replace this temporary context boundary with canonical links."""
    store = _store(tmp_path)
    payload = b"shared evidence bytes"

    first = _upload(store, payload, project_id="project-1")
    second = _upload(store, payload, project_id="project-2")

    assert second.media_id != first.media_id
    assert len(store.records("organization-1")) == 2
