"""Supervised durable job workers with bounded resource-class pools."""

from __future__ import annotations

import json
import os
import threading
import time
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


class DatabaseCancellationToken:
    def __init__(self, factory: SqliteConnectionFactory, public_id: str) -> None:
        self.factory, self.public_id = factory, public_id

    def raise_if_cancelled(self) -> None:
        connection = self.factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT cancellation_requested,pause_requested FROM jobs WHERE public_id=?",
                (self.public_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None or row["cancellation_requested"]:
            raise JobCancelled(self.public_id)
        if row["pause_requested"]:
            raise JobPaused(self.public_id)


@dataclass(slots=True)
class ExecutionContext:
    job: JobRecord
    cancellation: DatabaseCancellationToken
    factory: SqliteConnectionFactory
    now_us: Callable[[], int]

    def report_progress(
        self, current: int, total: int | None, unit: str | None, message: str | None
    ) -> None:
        self.cancellation.raise_if_cancelled()
        with SqliteUnitOfWork(self.factory) as uow:
            uow.jobs.update_progress(
                self.job.public_id,
                current=current,
                total=total,
                unit=unit,
                message=message,
                now_us=self.now_us(),
            )
            uow.commit()


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
        with SqliteUnitOfWork(self.factory) as uow:
            job = uow.jobs.claim_next(
                resource_class=resource,
                worker_id=self.worker_id,
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
        handler = self.handlers.get(job.job_type)
        if handler is None:
            self._finish(job, JobState.FAILED, error="unknown_job_type")
            return
        context = ExecutionContext(
            job, DatabaseCancellationToken(self.factory, job.public_id), self.factory, self._now
        )
        try:
            result = handler.execute(context)
            context.cancellation.raise_if_cancelled()
            self._finish(
                job,
                JobState.SUCCEEDED,
                result=json.dumps(result or {}, sort_keys=True, separators=(",", ":")),
            )
        except JobCancelled:
            self._finish(job, JobState.CANCELLED)
        except JobPaused:
            self._finish(job, JobState.PAUSED)
        except Exception as exc:
            self._finish(job, JobState.FAILED, error=type(exc).__name__)

    def _finish(
        self,
        job: JobRecord,
        state: JobState,
        *,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        with SqliteUnitOfWork(self.factory) as uow:
            uow.jobs.finish(
                job.public_id, state=state, now_us=self._now(), result_json=result, error_code=error
            )
            uow.commit()

    @staticmethod
    def _now() -> int:
        return int(datetime.now(UTC).timestamp() * 1_000_000)
