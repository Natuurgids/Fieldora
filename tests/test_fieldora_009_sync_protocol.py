from pathlib import Path

from natureai_next.application.sync_coordinator import DesktopSyncCoordinator
from natureai_next.application.synchronization import DesktopSynchronizationService
from natureai_next.domain.sync_protocol import PullPage, PushDisposition, PushResult
from natureai_next.domain.synchronization import (
    EnrollmentState,
    ContributionAcknowledgment,
    PlatformAccount,
    ProjectEnrollment,
    SyncChange,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS, MigrationRunner
from natureai_next.infrastructure.database.synchronization import (
    SqliteDesktopSynchronizationRepository,
)


class FakeTransport:
    def __init__(self) -> None:
        self.push_results = ()
        self.pull_page = PullPage("e", (), "", False)

    def push(self, *, enrollment_id, changes):
        return self.push_results

    def pull(self, *, enrollment_id, cursor, limit):
        return self.pull_page


def _setup(tmp_path: Path):
    factory = SqliteConnectionFactory(tmp_path / "library.sqlite3")
    with factory.connect() as connection:
        MigrationRunner(CORE_MIGRATIONS, "0.09.2").apply(connection)
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
    repository.acknowledge_contribution(
        ContributionAcknowledgment(
            "ack", "e", 1, "license-1", "a" * 64, "user",
            "2026-01-01T00:00:00+00:00",
        )
    )
    return repository, service, FakeTransport()


def test_push_maps_results_to_completion_retry_and_conflict(tmp_path: Path) -> None:
    repository, service, transport = _setup(tmp_path)
    changes = (
        SyncChange("c1", "e", "i1", "dossier", "d1", 1, {"v": 1}, False),
        SyncChange("c2", "e", "i2", "dossier", "d2", 1, {"v": 2}, False),
        SyncChange("c3", "e", "i3", "dossier", "d3", 1, {"v": 3}, False),
    )
    for change in changes:
        service.queue_contribution(change, at_utc="2026-08-01T00:00:00+00:00")
    transport.push_results = (
        PushResult("c1", PushDisposition.APPLIED, 2),
        PushResult("c2", PushDisposition.RETRY, retry_at_utc="2026-08-01T01:00:00+00:00"),
        PushResult("c3", PushDisposition.CONFLICT, 4, {"v": 4}),
    )
    coordinator = DesktopSyncCoordinator(repository, transport)
    assert coordinator.push_once(
        "e", now_utc="2026-08-01T00:00:00+00:00",
        lease_until_utc="2026-08-01T00:05:00+00:00",
    ) == 3
    assert repository.conflicts("e")[0].remote_revision == 4
    retry = repository.claim_outbox(
        enrollment_id="e",
        now_utc="2026-08-01T01:00:00+00:00",
        lease_until_utc="2026-08-01T01:05:00+00:00", limit=10,
    )
    assert [item.change_id for item in retry] == ["c2"]


def test_pull_is_idempotent_and_advances_cursor_after_acceptance(tmp_path: Path) -> None:
    repository, _service, transport = _setup(tmp_path)
    remote = SyncChange("r1", "e", "remote-1", "asset", "a1", 5, {}, True)
    transport.pull_page = PullPage("e", (remote,), "cursor-6", False)
    coordinator = DesktopSyncCoordinator(repository, transport)
    assert coordinator.pull_once("e", at_utc="2026-08-01T00:00:00+00:00") == 1
    assert coordinator.pull_once("e", at_utc="2026-08-01T00:00:00+00:00") == 1
    assert repository.cursor("e") == "cursor-6"


def test_revoked_rights_block_transport(tmp_path: Path) -> None:
    repository, service, transport = _setup(tmp_path)
    service.enroll_project(
        ProjectEnrollment(
            "replacement", "a", "p", "c", EnrollmentState.REVOKED,
            ("view", "contribute"), "2027-01-01T00:00:00+00:00", 2,
            "2026-01-01T00:00:00+00:00",
        )
    )
    coordinator = DesktopSyncCoordinator(repository, transport)
    for operation in (
        lambda: coordinator.push_once(
            "e", now_utc="2026-08-01T00:00:00+00:00",
            lease_until_utc="2026-08-01T00:05:00+00:00",
        ),
        lambda: coordinator.pull_once("e", at_utc="2026-08-01T00:00:00+00:00"),
    ):
        try:
            operation()
        except PermissionError:
            pass
        else:
            raise AssertionError("revoked enrollment reached transport")
