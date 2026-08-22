from pathlib import Path

from natureai_next.server.exports import GovernedExportStore


class MemoryObjects:
    def __init__(self) -> None:
        self.items: dict[str, bytes] = {}

    def put(self, key: str, source: Path, mime_type: str, sha256: str) -> None:
        assert mime_type == "application/zip"
        assert len(sha256) == 64
        self.items[key] = source.read_bytes()

    def read_range(self, key: str, start: int, end: int) -> bytes:
        return self.items[key][start : end + 1]

    def delete(self, key: str) -> None:
        self.items.pop(key, None)


def test_governed_exports_use_replaceable_object_storage(tmp_path: Path) -> None:
    objects = MemoryObjects()
    store = GovernedExportStore(
        tmp_path / "exports.sqlite3",
        tmp_path / "staging",
        object_store=objects,
    )
    record = store.create(
        "job-1",
        "subject-1",
        "tenant-a",
        "project-1",
        lambda path: path.write_bytes(b"export payload"),
    )
    assert store.read_range(record, 0, 5) == b"export"
    assert record.relative_path in objects.items
    assert store.revoke(record.export_id)
    assert record.relative_path not in objects.items


def test_production_worker_uses_shared_backends_and_continuous_polling() -> None:
    root = Path(__file__).parents[1]
    manifest = (root / "deployment/kubernetes/base/platform.yaml").read_text()
    worker = manifest.split("name: fieldora-worker", 1)[1]
    for option in (
        "--access-backend",
        "--science-backend",
        "--job-backend",
        "--media-metadata-backend",
        "--export-metadata-backend",
        "--media-object-store",
        "--s3-export-prefix",
        "--search-backend",
        "--continuous",
    ):
        assert option in worker
    assert "emptyDir" in worker


def test_container_build_creates_runtime_root_and_excludes_local_state() -> None:
    root = Path(__file__).parents[1]
    dockerfile = (root / "deployment/container/Dockerfile").read_text()
    ignore = (root / ".dockerignore").read_text()
    assert "mkdir -p /var/lib/fieldora" in dockerfile
    assert "PYTHON_BASE_IMAGE" in dockerfile
    assert "ApertureData" in ignore
    assert "web/excalidraw/node_modules" in ignore
    assert "*.zip" in ignore
