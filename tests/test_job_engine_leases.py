from pathlib import Path

import pytest

from natureai_next.domain.jobs import JobRecord, JobState, ResourceClass
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS, MigrationRunner
from natureai_next.infrastructure.database.unit_of_work import SqliteUnitOfWork
from natureai_next.jobs.engine import (
    DatabaseCancellationToken,
    ExecutionContext,
    JobEngine,
    JobLeaseLost,
)


def _factory(tmp_path: Path) -> SqliteConnectionFactory:
    factory = SqliteConnectionFactory(tmp_path / "jobs.sqlite3")
    connection = factory.connect()
    try:
        MigrationRunner(CORE_MIGRATIONS, "test").apply(connection)
    finally:
        connection.close()
    return factory


def _queued_job(public_id: str = "job-1") -> JobRecord:
    return JobRecord(
        public_id=public_id,
        job_type="test",
        payload_version=1,
        payload_json="{}",
        state=JobState.QUEUED,
        priority=0,
        resource_class=ResourceClass.IO,
        created_at_us=1,
        modified_at_us=1,
    )


def _claim(
    factory: SqliteConnectionFactory,
    *,
    owner: str,
    now_us: int,
    lease_until_us: int,
) -> JobRecord:
    with SqliteUnitOfWork(factory) as uow:
        claimed = uow.jobs.claim_next(
            resource_class=ResourceClass.IO,
            worker_id=owner,
            now_us=now_us,
            lease_until_us=lease_until_us,
        )
        uow.commit()
    assert claimed is not None
    return claimed


def test_stale_claim_cannot_report_progress_or_finish_after_reclaim(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with SqliteUnitOfWork(factory) as uow:
        uow.jobs.add(_queued_job())
        uow.commit()

    first = _claim(factory, owner="worker:first", now_us=2, lease_until_us=10)

    with SqliteUnitOfWork(factory) as uow:
        assert uow.jobs.recover_expired(now_us=11) == 1
        uow.connection.execute(
            "UPDATE jobs SET state='queued',modified_at_us=? WHERE public_id=? AND state='interrupted'",
            (11, first.public_id),
        )
        uow.commit()

    second = _claim(factory, owner="worker:second", now_us=12, lease_until_us=20)
    engine = JobEngine(factory, [], io_workers=0, cpu_workers=0)
    stale_context = ExecutionContext(
        first,
        DatabaseCancellationToken(factory, first.public_id, first.lease_owner),
        factory,
        lambda: 13,
        first.lease_owner,
    )

    with pytest.raises(JobLeaseLost):
        stale_context.report_progress(1, 2, "item", "stale")
    assert engine._finish(first, JobState.SUCCEEDED, result='{"stale":true}') is False

    connection = factory.connect(read_only=True)
    try:
        row = connection.execute(
            "SELECT state,lease_owner,progress_current,result_json FROM jobs WHERE public_id=?",
            (first.public_id,),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    assert row["state"] == JobState.RUNNING
    assert row["lease_owner"] == second.lease_owner
    assert row["progress_current"] == 0
    assert row["result_json"] is None

    assert engine._finish(second, JobState.SUCCEEDED, result='{"fresh":true}') is True


def test_heartbeat_renews_only_the_current_claim(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with SqliteUnitOfWork(factory) as uow:
        uow.jobs.add(_queued_job())
        uow.commit()

    claimed = _claim(factory, owner="worker:claim", now_us=2, lease_until_us=10)
    engine = JobEngine(factory, [], io_workers=0, cpu_workers=0, lease_seconds=30)

    class OneHeartbeat:
        calls = 0

        def wait(self, _timeout: float) -> bool:
            self.calls += 1
            return self.calls > 1

    engine._heartbeat_loop(claimed.public_id, claimed.lease_owner or "", OneHeartbeat())

    connection = factory.connect(read_only=True)
    try:
        renewed = connection.execute(
            "SELECT lease_owner,lease_expires_at_us FROM jobs WHERE public_id=?",
            (claimed.public_id,),
        ).fetchone()
    finally:
        connection.close()
    assert renewed is not None
    assert renewed["lease_owner"] == claimed.lease_owner
    assert renewed["lease_expires_at_us"] > 10

    connection = factory.connect()
    try:
        connection.execute(
            "UPDATE jobs SET lease_owner='worker:new' WHERE public_id=?",
            (claimed.public_id,),
        )
    finally:
        connection.close()

    previous_expiry = renewed["lease_expires_at_us"]
    engine._heartbeat_loop(claimed.public_id, claimed.lease_owner or "", OneHeartbeat())

    connection = factory.connect(read_only=True)
    try:
        current = connection.execute(
            "SELECT lease_owner,lease_expires_at_us FROM jobs WHERE public_id=?",
            (claimed.public_id,),
        ).fetchone()
    finally:
        connection.close()
    assert current is not None
    assert current["lease_owner"] == "worker:new"
    assert current["lease_expires_at_us"] == previous_expiry
