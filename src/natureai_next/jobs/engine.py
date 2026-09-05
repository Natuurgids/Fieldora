"""Supervised durable job workers with bounded resource-class pools."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from natureai_next.domain.jobs import JobRecord, JobState, ResourceClass
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.unit_of_work import SqliteUnitOfWork
from natureai_next.ports.jobs import JobHandler


class JobCancelled(RuntimeError):
    pass


class JobPaused(RuntimeError):
    pass


class JobLeaseLost(RuntimeError):
    pass


class DatabaseCancellationToken:
    def __init__(
        self,
        factory: SqliteConnectionFactory,
        public_id: str,
        expected_lease_owner: str | None = None,
    ) -> None:
        self.factory = factory
        self.public_id = public_id
        self.expected_lease_owner = expected_lease_owner

    def raise_if_cancelled(self) -> None:
        connection = self.factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT state,cancellation_requested,pause_requested,lease_owner "
                "FROM jobs WHERE public_id=?",
                (self.public_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise JobCancelled(self.public_id)
        if self.expected_lease_owner is not None and (
            row["state"] != JobState.RUNNING
            or row["lease_owner"] != self.expected_lease_owner
        ):
            raise JobLeaseLost(self.public_id)
        if row["cancellation_requested"]:
            raise JobCancelled(self.public_id)
        if row["pause_requested"]:
            raise JobPaused(self.public_id)


@dataclass(slots=True)
class ExecutionContext:
    job: JobRecord
    cancellation: DatabaseCancellationToken
    factory: SqliteConnectionFactory
    now_us: Callable[[], int]
    lease_owner: str | None = None

    def report_progress(
        self, current: int, total: int | None, unit: str | None, message: str | None
    ) -> None:
        self.cancellation.raise_if_cancelled()
        if current < 0 or (total is not None and (total < 0 or current > total)):
            raise ValueError("invalid job progress")
        owner = self.lease_owner or self.job.lease_owner
        if owner is None:
            raise JobLeaseLost(self.job.public_id)
        with SqliteUnitOfWork(self.factory) as uow:
            updated = uow.connection.execute(
                """UPDATE jobs SET progress_current=?,progress_total=?,progress_unit=?,
                   progress_message=?,modified_at_us=?
                   WHERE public_id=? AND state='running' AND lease_owner=?""",
                (
                    current,
                    total,
                    unit,
                    message,
                    self.now_us(),
                    self.job.public_id,
                    owner,
                ),
            )
            uow.commit()
        if updated.rowcount != 1:
            raise JobLeaseLost(self.job.public_id)


class JobEngine:
    def __init__(
        self,
        factory: SqliteConnectionFactory,
        handlers: list[JobHandler],
        *,
        io_workers: int | None = None,
        cpu_workers: int | None = None,
        poll_interval: float = 0.1,
        lease_seconds: int = 30,
        worker_id: str = "NatureAI_Nest",
    ) -> None:
        logical = max(2, os.cpu_count() or 2)
        io_workers = io_workers if io_workers is not None else min(8, max(2, logical // 2))
        cpu_workers = cpu_workers if cpu_workers is not None else min(8, max(2, logical - 2))
        self.factory = factory
        self.handlers = {h.job_type: h for h in handlers}
        self.pool_sizes = {
            ResourceClass.IO: io_workers,
            ResourceClass.CPU: cpu_workers,
            ResourceClass.GPU: 1,
        }
        self.poll_interval = poll_interval
        self.lease_us = lease_seconds * 1_000_000
        self.worker_id = worker_id
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if self._threads:
            return
        self.recover_interrupted()
        for resource, count in self.pool_sizes.items():
            for index in range(max(0, count)):
                thread = threading.Thread(
                    target=self._loop,
                    args=(resource,),
                    name=f"natureai-{resource}-{index}",
                    daemon=False,
                )
                thread.start()
                self._threads.append(thread)

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        deadline = time.monotonic() + timeout
        for thread in self._threads:
            thread.join(max(0, deadline - time.monotonic()))
        self._threads.clear()

    def recover_interrupted(self) -> int:
        with SqliteUnitOfWork(self.factory) as uow:
            count = uow.jobs.recover_expired(now_us=self._now())
            uow.connection.execute(
                "UPDATE jobs SET state='queued',retry_at_us=NULL,modified_at_us=? WHERE state='interrupted'",
                (self._now(),),
            )
            uow.commit()
            return count

    def run_once(self, resource: ResourceClass) -> bool:
        now = self._now()
        claim_owner = f"{self.worker_id}:{uuid.uuid4().hex}"
        with SqliteUnitOfWork(self.factory) as uow:
            job = uow.jobs.claim_next(
                resource_class=resource,
                worker_id=claim_owner,
                now_us=now,
                lease_until_us=now + self.lease_us,
            )
            uow.commit()
        if job is None:
            return False
        self._execute(job)
        return True

    def _loop(self, resource: ResourceClass) -> None:
        while not self._stop.is_set():
            if not self.run_once(resource):
                self._stop.wait(self.poll_interval)

    def _execute(self, job: JobRecord) -> None:
        owner = job.lease_owner
        if owner is None:
            raise JobLeaseLost(job.public_id)

        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(job.public_id, owner, heartbeat_stop),
            name=f"natureai-lease-{job.public_id}",
            daemon=True,
        )
        heartbeat.start()
        try:
            handler = self.handlers.get(job.job_type)
            if handler is None:
                self._finish(job, JobState.FAILED, error="unknown_job_type")
                return
            context = ExecutionContext(
                job,
                DatabaseCancellationToken(self.factory, job.public_id, owner),
                self.factory,
                self._now,
                owner,
            )
            try:
                result = handler.execute(context)
                context.cancellation.raise_if_cancelled()
                self._finish(
                    job,
                    JobState.SUCCEEDED,
                    result=json.dumps(result or {}, sort_keys=True, separators=(",", ":")),
                )
            except JobLeaseLost:
                return
            except JobCancelled:
                self._finish(job, JobState.CANCELLED)
            except JobPaused:
                self._finish(job, JobState.PAUSED)
            except Exception as exc:
                self._finish(job, JobState.FAILED, error=type(exc).__name__)
        finally:
            heartbeat_stop.set()
            heartbeat.join()

    def _heartbeat_loop(
        self, public_id: str, lease_owner: str, stop: threading.Event
    ) -> None:
        interval = max(0.1, self.lease_us / 3_000_000)
        while not stop.wait(interval):
            now = self._now()
            try:
                with SqliteUnitOfWork(self.factory) as uow:
                    updated = uow.connection.execute(
                        """UPDATE jobs SET lease_expires_at_us=?,modified_at_us=?
                           WHERE public_id=? AND state='running' AND lease_owner=?""",
                        (now + self.lease_us, now, public_id, lease_owner),
                    )
                    uow.commit()
            except Exception:
                return
            if updated.rowcount != 1:
                return

    def _finish(
        self,
        job: JobRecord,
        state: JobState,
        *,
        result: str | None = None,
        error: str | None = None,
    ) -> bool:
        if state not in {
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.PAUSED,
            JobState.QUEUED,
        }:
            raise ValueError("unsupported completion state")
        owner = job.lease_owner
        if owner is None:
            return False
        now = self._now()
        completed = (
            now if state in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED} else None
        )
        with SqliteUnitOfWork(self.factory) as uow:
            updated = uow.connection.execute(
                """UPDATE jobs SET state=?,result_json=?,error_code=?,retry_at_us=NULL,
                   completed_at_us=?,modified_at_us=?,lease_owner=NULL,lease_expires_at_us=NULL
                   WHERE public_id=? AND state='running' AND lease_owner=?""",
                (state, result, error, completed, now, job.public_id, owner),
            )
            uow.commit()
        return updated.rowcount == 1

    @staticmethod
    def _now() -> int:
        return int(datetime.now(UTC).timestamp() * 1_000_000)
