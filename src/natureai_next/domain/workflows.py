"""Workflow definitions and cleanup policy value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutionMode(StrEnum):
    """Supported workflow execution modes for the offline desktop runtime."""

    EMBEDDED = "embedded"


class CleanupTarget(StrEnum):
    JOBS = "jobs"
    OUTBOX = "outbox"
    TEMPORARY_FILES = "temporary_files"


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    step_id: str
    job_type: str
    resource_class: str
    depends_on: str | None = None
    optional: bool = False
    priority: int = 0
    execution_mode: ExecutionMode = ExecutionMode.EMBEDDED


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    workflow_id: str
    version: int
    steps: tuple[WorkflowStep, ...]

    def __post_init__(self) -> None:
        if not self.workflow_id.strip():
            raise ValueError("workflow_id is required")
        if self.version < 1:
            raise ValueError("workflow version must be positive")
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("workflow step IDs must be unique")
        known: set[str] = set()
        for step in self.steps:
            if not step.step_id.strip() or not step.job_type.strip():
                raise ValueError("workflow steps require IDs and job types")
            if step.execution_mode is not ExecutionMode.EMBEDDED:
                raise ValueError("Aperture workflows must execute in the embedded desktop runtime")
            if step.resource_class not in {"io", "cpu", "gpu"}:
                raise ValueError("workflow resource class must be io, cpu, or gpu")
            if step.depends_on is not None and step.depends_on not in known:
                raise ValueError("workflow dependencies must reference an earlier step")
            known.add(step.step_id)


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    succeeded_job_days: int = 30
    failed_job_days: int = 90
    cancelled_job_days: int = 30
    dispatched_event_days: int = 14
    temporary_file_days: int = 7
    keep_latest_jobs_per_type: int = 25

    def __post_init__(self) -> None:
        values = (
            self.succeeded_job_days,
            self.failed_job_days,
            self.cancelled_job_days,
            self.dispatched_event_days,
            self.temporary_file_days,
            self.keep_latest_jobs_per_type,
        )
        if any(value < 0 for value in values):
            raise ValueError("retention values cannot be negative")
