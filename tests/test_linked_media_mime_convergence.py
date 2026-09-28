from __future__ import annotations

from pathlib import Path

from natureai_next.server.linked_media_convergence import LinkedMediaConvergenceService
from natureai_next.server.linked_storage import (
    LinkedStorageCatalogue,
    LinkedStorageRepository,
    LinkedStorageSource,
)
from natureai_next.server.media import GovernedMediaStore


def test_linked_media_convergence_recovers_type_from_relative_filename(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    linked_file = archive / "survey" / "photo.jpg"
    linked_file.parent.mkdir(parents=True)
    linked_file.write_bytes(b"fieldora-linked-jpeg-evidence")

    repository = LinkedStorageRepository(tmp_path / "linked.sqlite3")
    repository.put_source(
        LinkedStorageSource("nas-1", "org-1", "Archive NAS", str(archive))
    )
    list(LinkedStorageCatalogue(repository).scan("nas-1", project_id="project-1"))
    linked = repository.media_in_path("nas-1")[0]

    # Reproduce the generic media identity that triggered the Library preview bug.
    with repository._connect() as connection:
        connection.execute(
            "UPDATE linked_media SET mime_type = ? WHERE media_id = ?",
            ("application/octet-stream", linked.media_id),
        )
        connection.commit()

    governed = GovernedMediaStore(tmp_path / "media.sqlite3", tmp_path / "managed")
    canonical = LinkedMediaConvergenceService(repository, governed).converge(
        linked.media_id, linked_by="researcher-1"
    )

    assert canonical.mime_type == "image/jpeg"
