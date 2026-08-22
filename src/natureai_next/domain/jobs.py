"""Durable job state, transition, progress, and item models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class JobItemState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResourceClass(StrEnum):
    IO = "io"
    CPU = "cpu"
    GPU = "gpu"


TERMINAL_JOB_STATES: Final[frozenset[JobState]] = frozenset(
    {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}
)

_ALLOWED_TRANSITIONS: Final[dict[JobState, frozenset[JobState]]] = {
    JobState.QUEUED: frozenset({JobState.RUNNING, JobState.PAUSED, JobState.CANCELLED}),
    JobState.RUNNING: frozenset(
        {
            JobState.QUEUED,
            JobState.PAUSED,
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.CANCELLED,
            JobState.INTERRUPTED,
        }
    ),
    JobState.PAUSED: frozenset({JobState.QUEUED, JobState.CANCELLED}),
    JobState.INTERRUPTED: frozenset({JobState.QUEUED, JobState.FAILED, JobState.CANCELLED}),
    JobState.FAILED: frozenset({JobState.QUEUED}),
    JobState.SUCCEEDED: frozenset(),
    JobState.CANCELLED: frozenset(),
}


def validate_job_transition(current: JobState, target: JobState) -> None:
    """Reject illegal state changes before persistence."""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"illegal job transition: {current.value} -> {target.value}")


@dataclass(frozen=True, slots=True)
class JobRecord:
    public_id: str
    job_type: str
    payload_version: int
    payload_json: str
    state: JobState
    priority: int
    resource_class: str
    created_at_us: int
    modified_at_us: int
    idempotency_key: str | None = None
    parent_job_id: int | None = None
    dependency_job_id: int | None = None
    progress_current: int = 0
    progress_total: int | None = None
    progress_unit: str | None = None
    progress_message: str | None = None
    attempt_count: int = 0
    retry_at_us: int | None = None
    started_at_us: int | None = None
    completed_at_us: int | None = None
    error_code: str | None = None
    diagnostic_reference: str | None = None
    result_json: str | None = None
    cancellation_requested: bool = False
    pause_requested: bool = False
    lease_owner: str | None = None
    lease_expires_at_us: int | None = None
    id: int | None = None


@dataclass(frozen=True, slots=True)
class JobItem:
    job_id: int
    item_key: str
    state: JobItemState
    modified_at_us: int
    attempt_count: int = 0
    payload_json: str | None = None
    result_json: str | None = None
    error_code: str | None = None
    id: int | None = None
