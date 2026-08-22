"""Job execution ports."""

from __future__ import annotations

from typing import Protocol

from natureai_next.domain.jobs import JobRecord


class CancellationToken(Protocol):
    def raise_if_cancelled(self) -> None: ...


class JobExecutionContext(Protocol):
    job: JobRecord
    cancellation: CancellationToken

    def report_progress(
        self, current: int, total: int | None, unit: str | None, message: str | None
    ) -> None: ...


class JobHandler(Protocol):
    job_type: str
    resource_class: str

    def execute(self, context: JobExecutionContext) -> dict[str, object] | None: ...


class JobCommandStore(Protocol):
    def submit(self, record: JobRecord) -> JobRecord: ...
    def request_cancel(self, public_id: str, now_us: int) -> bool: ...
    def request_pause(self, public_id: str, now_us: int) -> bool: ...
    def resume(self, public_id: str, now_us: int) -> bool: ...
    def restart_completed(self, public_id: str, now_us: int) -> bool: ...
    def list_recent(self, limit: int = 100) -> tuple[JobRecord, ...]: ...
