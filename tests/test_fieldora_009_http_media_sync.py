import hashlib
from pathlib import Path

from natureai_next.application.media_sync import ResumableMediaDownloadService
from natureai_next.application.synchronization import DesktopSynchronizationService
from natureai_next.domain.synchronization import (
    EnrollmentState,
    MediaTransfer,
    PlatformAccount,
    ProjectEnrollment,
    SyncChange,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS, MigrationRunner
from natureai_next.infrastructure.database.synchronization import (
    SqliteDesktopSynchronizationRepository,
)
from natureai_next.infrastructure.http_sync import HttpSynchronizationTransport


def _repository(tmp_path: Path):
    factory = SqliteConnectionFactory(tmp_path / "library.sqlite3")
    with factory.connect() as connection:
        MigrationRunner(CORE_MIGRATIONS, "0.09.3").apply(connection)
    repository = SqliteDesktopSynchronizationRepository(factory)
    service = DesktopSynchronizationService(repository)
    service.save_account(
        PlatformAccount("a", "https://fieldora.example", "Account", "org", "user", "now")
    )
    service.enroll_project(
        ProjectEnrollment(
            "e", "a", "p", "c", EnrollmentState.ACTIVE, ("view", "contribute"),
            "2027-01-01T00:00:00+00:00", 1, "2026-01-01T00:00:00+00:00",
        )
    )
    return repository


class FakeHttp:
    def __init__(self) -> None:
        self.requests = []

    def request_json(self, method, path, *, token, body=None):
        self.requests.append((method, path, token, body))
        if path.endswith("/push"):
            return {
                "protocol_version": 1,
                "results": [{"change_id": "c", "disposition": "applied",
                             "remote_revision": 2}],
            }
        return {
            "protocol_version": 1, "enrollment_id": "e", "changes": [],
            "next_cursor": "cursor-1", "has_more": False,
        }


def test_http_binding_uses_versioned_paths_token_and_payload() -> None:
    client = FakeHttp()
    transport = HttpSynchronizationTransport(client, lambda: "machine-token")
    change = SyncChange("c", "e", "idem", "asset", "a1", 1, {}, False)
    assert transport.push(enrollment_id="e", changes=(change,))[0].remote_revision == 2
    assert transport.pull(enrollment_id="e", cursor="", limit=100).next_cursor == "cursor-1"
    assert all(request[1].startswith("/api/v1/sync/") for request in client.requests)
    assert all(request[2] == "machine-token" for request in client.requests)
    assert all(request[3]["protocol_version"] == 1 for request in client.requests)


class RangeSource:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offsets = []

    def read_range(self, *, media_id, offset, length, etag):
        self.offsets.append(offset)
        return self.data[offset : offset + length], etag


def test_media_download_resumes_from_durable_offset_and_verifies_hash(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    data = b"0123456789"
    target = tmp_path / "downloads" / "asset.bin"
    repository.put_media_transfer(
        MediaTransfer(
            "t", "e", "media-1", str(target), len(data),
            hashlib.sha256(data).hexdigest(), "etag-1",
        )
    )
    source = RangeSource(data)
    service = ResumableMediaDownloadService(repository, source)
    assert service.run_chunk("t", chunk_size=4).offset == 4
    # Simulate bytes written after the last durable checkpoint before a crash.
    with target.open("ab") as stream:
        stream.write(b"garbage")
    assert service.run_chunk("t", chunk_size=4).offset == 8
    complete = service.run_chunk("t", chunk_size=4)
    assert complete.state == "complete"
    assert target.read_bytes() == data
    assert source.offsets == [0, 4, 8]
