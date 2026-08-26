from __future__ import annotations

from pathlib import Path

import pytest

from natureai_next.server.linked_media_convergence import LinkedMediaConvergenceService
from natureai_next.server.linked_storage import (
    LinkedStorageCatalogue,
    LinkedStorageRepository,
    LinkedStorageSource,
)
from natureai_next.server.media import GovernedMediaStore


def _catalogued_linked_file(
    tmp_path: Path,
    *,
    payload: bytes = b"fieldora-linked-evidence",
    project_id: str = "project-1",
):
    archive = tmp_path / "archive"
    linked_file = archive / "collection" / "sample.bin"
    linked_file.parent.mkdir(parents=True)
    linked_file.write_bytes(payload)
    repository = LinkedStorageRepository(tmp_path / "linked.sqlite3")
    repository.put_source(
        LinkedStorageSource("nas-1", "org-1", "Archive NAS", str(archive))
    )
    list(LinkedStorageCatalogue(repository).scan("nas-1", project_id=project_id))
    record = repository.media_in_path("nas-1")[0]
    return repository, linked_file, record


def test_verified_linked_file_becomes_referenced_canonical_media(tmp_path: Path) -> None:
    repository, linked_file, linked = _catalogued_linked_file(tmp_path)
    managed_root = tmp_path / "managed"
    governed = GovernedMediaStore(tmp_path / "media.sqlite3", managed_root)

    canonical = LinkedMediaConvergenceService(repository, governed).converge(
        linked.media_id, linked_by="researcher-1"
    )

    assert canonical.relative_path is None
    assert canonical.organization_id == "org-1"
    assert canonical.project_id == "project-1"
    instances = governed.instances(canonical.media_id, "org-1")
    assert len(instances) == 1
    assert instances[0].storage_kind == "referenced"
    assert instances[0].source_ref.startswith("linked:")
    assert "nas-1" not in instances[0].source_ref
    assert "sample.bin" not in instances[0].source_ref
    links = governed.associations.links(canonical.media_id, "org-1")
    assert [(link.association_type, link.target_id) for link in links] == [
        ("project", "project-1")
    ]
    assert not any(path.is_file() for path in managed_root.rglob("*"))
    assert linked_file.read_bytes() == b"fieldora-linked-evidence"
    assert repository.media(linked.media_id).sha256 == canonical.sha256  # type: ignore[union-attr]


def test_linked_verification_converges_with_existing_managed_bytes(tmp_path: Path) -> None:
    payload = b"same-scientific-evidence"
    repository, _, linked = _catalogued_linked_file(tmp_path, payload=payload)
    managed_source = tmp_path / "upload.bin"
    managed_source.write_bytes(payload)
    governed = GovernedMediaStore(tmp_path / "media.sqlite3", tmp_path / "managed")
    managed = governed.register(managed_source, "org-1", "managed-project")

    canonical = LinkedMediaConvergenceService(repository, governed).converge(
        linked.media_id, linked_by="researcher-1"
    )

    assert canonical.media_id == managed.media_id
    assert {instance.storage_kind for instance in governed.instances(canonical.media_id, "org-1")} == {
        "managed",
        "referenced",
    }
    assert {link.target_id for link in governed.associations.links(canonical.media_id, "org-1")} == {
        "project-1"
    }


def test_later_managed_upload_preserves_referenced_canonical_identity(tmp_path: Path) -> None:
    payload = b"referenced-first-evidence"
    repository, _, linked = _catalogued_linked_file(tmp_path, payload=payload)
    governed = GovernedMediaStore(tmp_path / "media.sqlite3", tmp_path / "managed")
    referenced = LinkedMediaConvergenceService(repository, governed).converge(
        linked.media_id, linked_by="researcher-1"
    )
    managed_source = tmp_path / "later-upload.bin"
    managed_source.write_bytes(payload)

    managed = governed.register(managed_source, "org-1", "later-project")

    assert managed.media_id == referenced.media_id
    assert managed.relative_path is not None
    assert {instance.storage_kind for instance in governed.instances(managed.media_id, "org-1")} == {
        "managed",
        "referenced",
    }


def test_convergence_fails_closed_when_linked_file_changed_after_scan(tmp_path: Path) -> None:
    repository, linked_file, linked = _catalogued_linked_file(tmp_path)
    linked_file.write_bytes(b"changed-after-scan")
    governed = GovernedMediaStore(tmp_path / "media.sqlite3", tmp_path / "managed")

    with pytest.raises(ValueError, match="rescan required"):
        LinkedMediaConvergenceService(repository, governed).converge(
            linked.media_id, linked_by="researcher-1"
        )

    assert governed.records("org-1") == ()
