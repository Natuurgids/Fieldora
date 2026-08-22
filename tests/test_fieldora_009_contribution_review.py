from pathlib import Path

from natureai_next.application.contribution_review import ContributionReviewService
from natureai_next.application.sync_coordinator import DesktopSyncCoordinator
from natureai_next.application.synchronization import DesktopSynchronizationService
from natureai_next.domain.sync_protocol import PushDisposition, PushResult
from natureai_next.domain.synchronization import (
    ContributionAcknowledgment,
    EnrollmentState,
    PlatformAccount,
    ProjectEnrollment,
    SyncChange,
    SyncConflict,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS, MigrationRunner
from natureai_next.infrastructure.database.synchronization import (
    SqliteDesktopSynchronizationRepository,
)


class AppliedTransport:
    def push(self, *, enrollment_id, changes):
        return tuple(PushResult(item.change_id, PushDisposition.APPLIED) for item in changes)


def _setup(tmp_path: Path):
    factory = SqliteConnectionFactory(tmp_path / "library.sqlite3")
    with factory.connect() as connection:
        MigrationRunner(CORE_MIGRATIONS, "0.09.4").apply(connection)
    repository = SqliteDesktopSynchronizationRepository(factory)
    service = DesktopSynchronizationService(repository)
    service.save_account(
        PlatformAccount("a", "https://fieldora.example", "Account", "org", "user", "now")
    )
    service.enroll_project(
        ProjectEnrollment(
            "e", "a", "p", "c", EnrollmentState.ACTIVE, ("view", "contribute"),
            "2027-01-01T00:00:00+00:00", 3, "2026-01-01T00:00:00+00:00",
        )
    )
    return repository, service


def test_preview_and_current_terms_acknowledgment_gate_push(tmp_path: Path) -> None:
    repository, service = _setup(tmp_path)
    for change in (
        SyncChange("c1", "e", "i1", "dossier", "d1", 1, {"title": "A"}, False),
        SyncChange("c2", "e", "i2", "asset", "a1", 1, {}, True),
    ):
        service.queue_contribution(change, at_utc="2026-08-01T00:00:00+00:00")
    review = ContributionReviewService(repository)
    preview = review.preview("e")
    assert (preview.change_count, preview.creates_or_updates, preview.deletions) == (2, 1, 1)
    coordinator = DesktopSyncCoordinator(repository, AppliedTransport())
    try:
        coordinator.push_once(
            "e", now_utc="2026-08-01T00:00:00+00:00",
            lease_until_utc="2026-08-01T00:05:00+00:00",
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("push bypassed contribution acknowledgment")
    review.acknowledge(
        ContributionAcknowledgment(
            "ack", "e", 3, "CC-BY-4.0", "b" * 64, "user",
            "2026-08-01T00:00:00+00:00",
        )
    )
    assert coordinator.push_once(
        "e", now_utc="2026-08-01T00:00:00+00:00",
        lease_until_utc="2026-08-01T00:05:00+00:00",
    ) == 2


def test_conflict_resolution_is_explicit_and_single_use(tmp_path: Path) -> None:
    repository, _service = _setup(tmp_path)
    repository.put_conflict(
        SyncConflict("x", "e", "dossier", "d1", 2, 3, {"a": 1}, {"a": 2}, "now")
    )
    review = ContributionReviewService(repository)
    review.resolve("x", resolution="manual", payload={"a": 3}, resolved_at_utc="later")
    assert repository.conflicts("e") == ()
    try:
        review.resolve("x", resolution="accept_remote", payload={"a": 2}, resolved_at_utc="later")
    except ValueError:
        pass
    else:
        raise AssertionError("resolved conflict was resolved twice")


def test_qt_review_panel_exposes_preview_acknowledgment_and_resolution() -> None:
    source = (
        Path(__file__).parents[1] / "src/natureai_next/ui/qt/sync_review.py"
    ).read_text(encoding="utf-8")
    assert "Review and acknowledge terms" in source
    assert "Keep local" in source
    assert "Accept remote" in source
    assert "Manual merge" in source
