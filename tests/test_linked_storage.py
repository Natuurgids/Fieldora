from __future__ import annotations

from pathlib import Path

from PIL import Image

from natureai_next.server.linked_storage import (
    LinkedPreviewWorker,
    LinkedStorageCatalogue,
    LinkedStorageRepository,
    LinkedStorageSource,
    PreviewPriorityQueue,
    sha256_linked_file,
)


def _image(path: Path, size: tuple[int, int] = (1200, 800)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path, "JPEG")


def test_catalogue_keeps_originals_in_place_and_preserves_relative_paths(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    first = archive / "Expedition-A" / "Camera-1" / "one.jpg"
    second = archive / "Expedition-A" / "Camera-2" / "two.jpg"
    _image(first)
    _image(second)
    before = first.read_bytes()

    repository = LinkedStorageRepository(tmp_path / "linked.sqlite3")
    repository.put_source(
        LinkedStorageSource("nas-1", "org-1", "Archive NAS", str(archive))
    )
    checkpoints = list(
        LinkedStorageCatalogue(repository).scan("nas-1", batch_size=1)
    )

    assert checkpoints[-1].state == "completed"
    assert checkpoints[-1].registered == 2
    records = repository.media_in_path("nas-1", "Expedition-A")
    assert [record.relative_path for record in records] == [
        "Expedition-A/Camera-1/one.jpg",
        "Expedition-A/Camera-2/two.jpg",
    ]
    assert first.read_bytes() == before
    assert first.is_file() and second.is_file()


def test_catalogue_resume_is_idempotent(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    for index in range(5):
        _image(archive / "camera" / f"{index:03}.jpg", (32, 32))

    repository = LinkedStorageRepository(tmp_path / "linked.sqlite3")
    repository.put_source(LinkedStorageSource("nas", "org", "NAS", str(archive)))
    catalogue = LinkedStorageCatalogue(repository)
    iterator = catalogue.scan("nas", scan_id="scan-1", batch_size=2)
    first_checkpoint = next(iterator)
    assert first_checkpoint.registered == 2

    resumed = list(catalogue.scan("nas", scan_id="scan-1", batch_size=2))
    assert resumed[-1].registered == 5
    assert len(repository.media_in_path("nas", "camera")) == 5


def test_visible_directory_previews_preempt_background_work(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    _image(archive / "visible.jpg")
    _image(archive / "background.jpg")
    repository = LinkedStorageRepository(tmp_path / "linked.sqlite3")
    repository.put_source(LinkedStorageSource("nas", "org", "NAS", str(archive)))
    list(LinkedStorageCatalogue(repository).scan("nas"))
    records = repository.media_in_path("nas")
    visible = next(record for record in records if record.relative_path == "visible.jpg")
    background = next(record for record in records if record.relative_path == "background.jpg")

    queue = PreviewPriorityQueue()
    assert queue.request(background.media_id, queue.BACKGROUND, "bulk")
    assert queue.request(visible.media_id, queue.VISIBLE_DIRECTORY, "visible-directory")
    worker = LinkedPreviewWorker(repository, tmp_path / "previews", queue, maximum_edge=256)

    first = worker.run_one()
    assert first is not None
    assert first.media_id == visible.media_id
    assert first.thumbnail_state == "ready"
    preview = tmp_path / "previews" / first.thumbnail_key
    assert preview.is_file()
    with Image.open(preview) as image:
        assert max(image.size) <= 256

    second = worker.run_one()
    assert second is not None
    assert second.media_id == background.media_id
    assert second.thumbnail_state == "ready"


def test_priority_queue_deduplicates_and_allows_priority_upgrade(tmp_path: Path) -> None:
    queue = PreviewPriorityQueue(maximum=2)
    assert queue.request("m1", queue.BACKGROUND, "bulk")
    assert not queue.request("m1", queue.BACKGROUND, "bulk-again")
    assert queue.request("m1", queue.INTERACTIVE, "user-opened")
    request = queue.pop()
    assert request is not None
    assert request.media_id == "m1"
    assert request.priority == queue.INTERACTIVE
    assert len(queue) == 0


def test_hash_is_computed_without_relocating_source(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    file = archive / "sample.bin"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"fieldora-linked-evidence")
    source = LinkedStorageSource("nas", "org", "NAS", str(archive))

    digest = sha256_linked_file(source, "sample.bin")

    assert len(digest) == 64
    assert file.read_bytes() == b"fieldora-linked-evidence"


def test_linked_paths_cannot_escape_configured_storage_root(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    repository = LinkedStorageRepository(tmp_path / "linked.sqlite3")
    repository.put_source(LinkedStorageSource("nas", "org", "NAS", str(archive)))

    try:
        list(LinkedStorageCatalogue(repository).scan("nas", relative_root="../outside"))
    except ValueError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("path traversal must be rejected")
