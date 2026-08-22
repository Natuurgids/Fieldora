"""Workflow submission over the existing durable job system."""

from __future__ import annotations

from dataclasses import dataclass

from natureai_next.application.jobs import JobService, SubmitJob
from natureai_next.domain.jobs import JobRecord, ResourceClass
from natureai_next.domain.workflows import WorkflowDefinition


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    workflow_id: str
    version: int
    jobs: tuple[JobRecord, ...]


class WorkflowRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, WorkflowDefinition] = {}

    def register(self, definition: WorkflowDefinition) -> None:
        existing = self._definitions.get(definition.workflow_id)
        if existing is not None and existing.version >= definition.version:
            raise ValueError("workflow version must increase")
        self._definitions[definition.workflow_id] = definition

    def get(self, workflow_id: str) -> WorkflowDefinition:
        try:
            return self._definitions[workflow_id]
        except KeyError as exc:
            raise KeyError(f"unknown workflow: {workflow_id}") from exc


class WorkflowService:
    def __init__(self, jobs: JobService, registry: WorkflowRegistry) -> None:
        self.jobs = jobs
        self.registry = registry

    def start(self, workflow_id: str, payload: dict[str, object], *, run_key: str) -> WorkflowRun:
        definition = self.registry.get(workflow_id)
        created: list[JobRecord] = []
        by_step: dict[str, JobRecord] = {}
        for step in definition.steps:
            dependency = by_step.get(step.depends_on) if step.depends_on else None
            job = self.jobs.submit(
                SubmitJob(
                    job_type=step.job_type,
                    payload={
                        **payload,
                        "workflow_id": definition.workflow_id,
                        "workflow_version": definition.version,
                        "workflow_step_id": step.step_id,
                        "workflow_run_key": run_key,
                        "optional_step": step.optional,
                        "execution_mode": step.execution_mode.value,
                    },
                    resource_class=ResourceClass(step.resource_class),
                    priority=step.priority,
                    idempotency_key=f"workflow:{definition.workflow_id}:{definition.version}:{run_key}:{step.step_id}",
                    dependency_job_id=dependency.id if dependency else None,
                    parent_job_id=created[0].id if created else None,
                )
            )
            by_step[step.step_id] = job
            created.append(job)
        return WorkflowRun(definition.workflow_id, definition.version, tuple(created))
