from natureai_next.application.synchronization import DesktopSynchronizationService
from natureai_next.domain.synchronization import (
    EnrollmentState,
    PlatformAccount,
    ProjectEnrollment,
    RegisteredDesktopDevice,
    SyncChange,
    SyncItemState,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS, MigrationRunner
from natureai_next.infrastructure.database.synchronization import (
    SqliteDesktopSynchronizationRepository,
)


def test_endpoint_device_enrollment_and_default_deny_rights(tmp_path) -> None:
    factory = SqliteConnectionFactory(tmp_path / "library.sqlite3")
    with factory.connect() as connection:
        MigrationRunner(CORE_MIGRATIONS, "0.09.0").apply(connection)
    repository = SqliteDesktopSynchronizationRepository(factory)
    service = DesktopSynchronizationService(repository)
    account = PlatformAccount(
        "account-1", "https://fieldora.example", "Field station", "org-1", "user-1",
        "2026-07-29T00:00:00+00:00",
    )
    service.save_account(account)
    service.register_device(
        RegisteredDesktopDevice(
            "local-device-1", "account-1", "server-device-1", "Field laptop",
            "2026-07-29T00:01:00+00:00",
        )
    )
    service.enroll_project(
        ProjectEnrollment(
            "enrollment-1", "account-1", "project-1", "contract-1",
            EnrollmentState.ACTIVE, ("view", "contribute"),
            "2026-12-01T00:00:00+00:00", 1, "2026-07-29T00:02:00+00:00",
        )
    )
    assert repository.devices("account-1")[0].server_device_id == "server-device-1"
    assert service.rights_view(
        "account-1", at_utc="2026-08-01T00:00:00+00:00"
    ) == {"project-1": ("contribute", "view")}
    assert service.rights_view(
        "account-1", at_utc="2027-01-01T00:00:00+00:00"
    ) == {"project-1": ()}


def test_stale_enrollment_revision_cannot_restore_revoked_rights(tmp_path) -> None:
    factory = SqliteConnectionFactory(tmp_path / "library.sqlite3")
    with factory.connect() as connection:
        MigrationRunner(CORE_MIGRATIONS, "0.09.0").apply(connection)
    repository = SqliteDesktopSynchronizationRepository(factory)
    service = DesktopSynchronizationService(repository)
    service.save_account(
        PlatformAccount(
            "a", "https://fieldora.example", "Account", "org", "subject",
            "2026-07-29T00:00:00+00:00",
        )
    )
    for revision, state in ((2, EnrollmentState.REVOKED), (1, EnrollmentState.ACTIVE)):
        service.enroll_project(
            ProjectEnrollment(
                f"e-{revision}", "a", "p", "c", state, ("view",),
                "2027-01-01T00:00:00+00:00", revision,
                "2026-07-29T00:00:00+00:00",
            )
        )
    assert service.rights_view("a", at_utc="2026-08-01T00:00:00+00:00") == {"p": ()}


def _sync_repository(tmp_path):
    factory = SqliteConnectionFactory(tmp_path / "sync.sqlite3")
    with factory.connect() as connection:
        MigrationRunner(CORE_MIGRATIONS, "0.09.1").apply(connection)
    repository = SqliteDesktopSynchronizationRepository(factory)
    service = DesktopSynchronizationService(repository)
    service.save_account(
        PlatformAccount("a", "https://fieldora.example", "Account", "org", "subject", "now")
    )
    service.enroll_project(
        ProjectEnrollment(
            "e", "a", "p", "c", EnrollmentState.ACTIVE, ("view", "contribute"),
            "2027-01-01T00:00:00+00:00", 1, "2026-01-01T00:00:00+00:00",
        )
    )
    return repository, service


def test_outbox_resumes_after_interrupted_lease_and_is_idempotent(tmp_path) -> None:
    repository, service = _sync_repository(tmp_path)
    change = SyncChange("change-1", "e", "idem-1", "dossier", "d1", 3, {"title": "Bat"}, False)
    assert service.queue_contribution(change, at_utc="2026-08-01T00:00:00+00:00")
    assert not service.queue_contribution(change, at_utc="2026-08-01T00:00:00+00:00")
    first = repository.claim_outbox(
        enrollment_id="e",
        now_utc="2026-08-01T00:00:00+00:00",
        lease_until_utc="2026-08-01T00:05:00+00:00",
        limit=10,
    )
    assert first[0].attempt_count == 1
    assert repository.claim_outbox(
        enrollment_id="e",
        now_utc="2026-08-01T00:04:00+00:00",
        lease_until_utc="2026-08-01T00:09:00+00:00",
        limit=10,
    ) == ()
    recovered = repository.claim_outbox(
        enrollment_id="e",
        now_utc="2026-08-01T00:06:00+00:00",
        lease_until_utc="2026-08-01T00:11:00+00:00",
        limit=10,
    )
    assert recovered[0].attempt_count == 2
    repository.complete_outbox("change-1")
    assert repository.claim_outbox(
        enrollment_id="e",
        now_utc="2026-08-01T00:12:00+00:00",
        lease_until_utc="2026-08-01T00:17:00+00:00",
        limit=10,
    ) == ()


def test_inbox_tombstone_cursor_and_revocation_guard(tmp_path) -> None:
    repository, service = _sync_repository(tmp_path)
    tombstone = SyncChange(
        "remote-1", "e", "remote-idem-1", "asset", "asset-1", 9, {}, True,
        SyncItemState.PENDING,
    )
    assert repository.accept_inbox(tombstone)
    assert not repository.accept_inbox(tombstone)
    repository.put_cursor("e", "cursor-10")
    assert repository.cursor("e") == "cursor-10"
    service.enroll_project(
        ProjectEnrollment(
            "e-new", "a", "p", "c", EnrollmentState.REVOKED, ("contribute",),
            "2027-01-01T00:00:00+00:00", 2, "2026-01-01T00:00:00+00:00",
        )
    )
    try:
        service.queue_contribution(
            SyncChange("change-2", "e", "idem-2", "asset", "asset-2", 0, {}, False),
            at_utc="2026-08-01T00:00:00+00:00",
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("revoked enrollment accepted a contribution")
