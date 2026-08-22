"""Application-facing durable job commands and queries."""

from __future__ import annotations

import json
from dataclasses import dataclass

from natureai_next.domain.jobs import JobRecord, JobState, ResourceClass
from natureai_next.ports.clock import Clock
from natureai_next.ports.identity import UuidGenerator
from natureai_next.ports.jobs import JobCommandStore


@dataclass(frozen=True, slots=True)
class SubmitJob:
    job_type: str
    payload: dict[str, object]
    resource_class: ResourceClass
    priority: int = 0
    payload_version: int = 1
    idempotency_key: str | None = None
    parent_job_id: int | None = None
    dependency_job_id: int | None = None


class JobService:
    def __init__(self, store: JobCommandStore, clock: Clock, ids: UuidGenerator) -> None:
        self.store, self.clock, self.ids = store, clock, ids

    def submit(self, command: SubmitJob) -> JobRecord:
        now = self._now()
        record = JobRecord(
            str(self.ids.new_uuid()),
            command.job_type,
            command.payload_version,
            json.dumps(command.payload, sort_keys=True, separators=(",", ":")),
            JobState.QUEUED,
            command.priority,
            command.resource_class,
            now,
            now,
            command.idempotency_key,
            command.parent_job_id,
            command.dependency_job_id,
        )
        return self.store.submit(record)

    def cancel(self, public_id: str) -> bool:
        return self.store.request_cancel(public_id, self._now())

    def pause(self, public_id: str) -> bool:
        return self.store.request_pause(public_id, self._now())

    def resume(self, public_id: str) -> bool:
        return self.store.resume(public_id, self._now())

    def restart_completed(self, public_id: str) -> bool:
        return self.store.restart_completed(public_id, self._now())

    def recent(self, limit: int = 100) -> tuple[JobRecord, ...]:
        return self.store.list_recent(limit)

    def _now(self) -> int:
        return int(self.clock.now_utc().timestamp() * 1_000_000)
