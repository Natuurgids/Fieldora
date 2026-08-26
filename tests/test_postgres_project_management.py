from __future__ import annotations

import os
from uuid import uuid4

import pytest

from natureai_next.server.postgres_project_management import (
    PostgresProjectManagementService,
)


def _connect_factory():
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    psycopg = pytest.importorskip("psycopg")
    return lambda: psycopg.connect(dsn, connect_timeout=10)


@pytest.mark.integration
def test_managed_project_creation_matches_desktop_contract() -> None:
    service = PostgresProjectManagementService(_connect_factory())
    organization_id = f"org-{uuid4()}"
    actor_id = f"user-{uuid4()}"

    project_id = service.create_project(
        "Wetland Survey",
        organization_id=organization_id,
        owner_id=actor_id,
        actor_id=actor_id,
        start_date="2026-09-01",
        due_date="2026-12-31",
        description="Seasonal field survey",
        budget=1250.5,
        currency="EUR",
    )

    projects = service.projects(organization_id)
    project = next(item for item in projects if item.project_id == project_id)
    assert project.name == "Wetland Survey"
    assert project.status == "active"
    assert project.owner_id == actor_id
    assert project.start_date == "2026-09-01"
    assert project.due_date == "2026-12-31"
    assert project.budget == 1250.5
    assert project.currency == "EUR"
    assert project.description == "Seasonal field survey"
    assert project.revision > 0

    statuses = service.statuses(project_id)
    assert [item["name"] for item in statuses] == [
        "To Do",
        "In Progress",
        "QA",
        "Blocked",
        "Done",
    ]
    assert [item["category"] for item in statuses] == [
        "todo",
        "active",
        "review",
        "blocked",
        "done",
    ]
    assert [item["color"] for item in statuses] == [
        "#6b7280",
        "#2563eb",
        "#7c3aed",
        "#dc2626",
        "#16a34a",
    ]
    assert [item["display_order"] for item in statuses] == [0, 1, 2, 3, 4]
    assert service.member_role(project_id, actor_id) == "admin"

    activity = service.activity(project_id)
    assert len(activity) == 1
    assert activity[0]["actor_id"] == actor_id
    assert activity[0]["event_type"] == "project.created"
    assert activity[0]["details"] == {"name": "Wetland Survey"}


@pytest.mark.integration
def test_managed_projects_are_organization_isolated() -> None:
    service = PostgresProjectManagementService(_connect_factory())
    organization_a = f"org-a-{uuid4()}"
    organization_b = f"org-b-{uuid4()}"
    actor = f"user-{uuid4()}"

    project_a = service.create_project(
        "Organization A Project",
        organization_id=organization_a,
        owner_id=actor,
        actor_id=actor,
    )
    project_b = service.create_project(
        "Organization B Project",
        organization_id=organization_b,
        owner_id=actor,
        actor_id=actor,
    )

    assert [item.project_id for item in service.projects(organization_a)] == [project_a]
    assert [item.project_id for item in service.projects(organization_b)] == [project_b]


@pytest.mark.integration
def test_invalid_project_dates_create_no_project() -> None:
    service = PostgresProjectManagementService(_connect_factory())
    organization_id = f"org-{uuid4()}"
    actor = f"user-{uuid4()}"
    before = {item.project_id for item in service.projects(organization_id)}

    with pytest.raises(ValueError, match="cannot be before"):
        service.create_project(
            "Impossible Schedule",
            organization_id=organization_id,
            owner_id=actor,
            actor_id=actor,
            start_date="2026-12-31",
            due_date="2026-01-01",
        )

    after = {item.project_id for item in service.projects(organization_id)}
    assert after == before


@pytest.mark.integration
def test_managed_project_update_archive_and_revision_conflict() -> None:
    service = PostgresProjectManagementService(_connect_factory())
    organization_id = f"org-lifecycle-{uuid4()}"
    actor = f"user-{uuid4()}"
    project_id = service.create_project(
        "Lifecycle Project",
        organization_id=organization_id,
        owner_id=actor,
        actor_id=actor,
        start_date="2026-09-01",
        due_date="2026-12-31",
        description="Before edit",
        budget=100,
        currency="EUR",
    )
    created = next(item for item in service.projects(organization_id) if item.project_id == project_id)

    edited_revision = service.update_project(
        project_id,
        organization_id=organization_id,
        actor_id=actor,
        expected_revision=created.revision,
        name="Lifecycle Project Updated",
        description="After edit",
        start_date="2026-09-15",
        due_date="2027-01-31",
        budget=250.75,
        currency="USD",
    )
    edited = next(item for item in service.projects(organization_id) if item.project_id == project_id)
    assert edited.revision == edited_revision
    assert edited.revision > created.revision
    assert edited.name == "Lifecycle Project Updated"
    assert edited.description == "After edit"
    assert edited.start_date == "2026-09-15"
    assert edited.due_date == "2027-01-31"
    assert edited.budget == 250.75
    assert edited.currency == "USD"
    assert edited.status == "active"

    with pytest.raises(ValueError, match="revision conflict"):
        service.update_project(
            project_id,
            organization_id=organization_id,
            actor_id=actor,
            expected_revision=created.revision,
            name="Stale overwrite",
        )
    after_conflict = next(
        item for item in service.projects(organization_id) if item.project_id == project_id
    )
    assert after_conflict.name == "Lifecycle Project Updated"
    assert after_conflict.revision == edited_revision

    archived_revision = service.archive_project(
        project_id,
        organization_id=organization_id,
        actor_id=actor,
        expected_revision=edited_revision,
    )
    archived = next(item for item in service.projects(organization_id) if item.project_id == project_id)
    assert archived.status == "archived"
    assert archived.revision == archived_revision
    assert archived.revision > edited_revision

    events = service.activity(project_id)
    assert [item["event_type"] for item in events] == [
        "project.created",
        "project.updated",
        "project.archived",
    ]
    assert events[1]["details"]["name"] == "Lifecycle Project Updated"
    assert events[2]["details"] == {"status": "archived"}


@pytest.mark.integration
def test_managed_project_update_validates_dates_and_organization() -> None:
    service = PostgresProjectManagementService(_connect_factory())
    organization_id = f"org-update-{uuid4()}"
    other_organization = f"org-other-{uuid4()}"
    actor = f"user-{uuid4()}"
    project_id = service.create_project(
        "Validated Project",
        organization_id=organization_id,
        owner_id=actor,
        actor_id=actor,
        start_date="2026-09-01",
        due_date="2026-12-31",
    )
    project = next(item for item in service.projects(organization_id) if item.project_id == project_id)

    with pytest.raises(ValueError, match="cannot be before"):
        service.update_project(
            project_id,
            organization_id=organization_id,
            actor_id=actor,
            expected_revision=project.revision,
            start_date="2027-01-01",
            due_date="2026-12-31",
        )
    with pytest.raises(KeyError):
        service.update_project(
            project_id,
            organization_id=other_organization,
            actor_id=actor,
            expected_revision=project.revision,
            name="Cross-org overwrite",
        )

    current = next(item for item in service.projects(organization_id) if item.project_id == project_id)
    assert current.name == "Validated Project"
    assert current.revision == project.revision


@pytest.mark.integration
def test_managed_project_children_match_desktop_hierarchy_contract() -> None:
    service = PostgresProjectManagementService(_connect_factory())
    organization_id = f"org-children-{uuid4()}"
    actor = f"user-{uuid4()}"
    project_id = service.create_project(
        "Hierarchy Project",
        organization_id=organization_id,
        owner_id=actor,
        actor_id=actor,
    )

    phase_id = service.create_phase(
        project_id,
        "Field season",
        organization_id=organization_id,
        actor_id=actor,
        description="Primary survey phase",
        planned_budget=800,
    )
    sprint_id = service.create_sprint(
        project_id,
        "September sprint",
        organization_id=organization_id,
        actor_id=actor,
        start_date="2026-09-01",
        end_date="2026-09-14",
        goal="Complete first transects",
    )
    task_id = service.create_task(
        project_id,
        "Survey transect A",
        organization_id=organization_id,
        actor_id=actor,
        phase_id=phase_id,
        sprint_id=sprint_id,
        owner_id=actor,
        description="Record all observations",
        estimate_hours=6.5,
    )
    subtask_id = service.create_task(
        project_id,
        "Photograph voucher specimens",
        organization_id=organization_id,
        actor_id=actor,
        parent_task_id=task_id,
        phase_id=phase_id,
        owner_id=actor,
        estimate_hours=1.5,
    )
    allocation_id = service.create_allocation(
        project_id,
        actor,
        organization_id=organization_id,
        actor_id=actor,
        start_date="2026-09-01",
        end_date="2026-09-30",
        hours_per_week=24,
        allocation_percent=60,
        role="field lead",
        phase_id=phase_id,
    )

    phases = service.phases(organization_id)
    sprints = service.sprints(organization_id)
    tasks = service.tasks(organization_id)
    allocations = service.allocations(organization_id)
    assert [item["id"] for item in phases] == [phase_id]
    assert phases[0]["project_id"] == project_id
    assert phases[0]["planned_budget"] == 800
    assert [item["id"] for item in sprints] == [sprint_id]
    assert sprints[0]["status"] == "planned"
    assert sprints[0]["goal"] == "Complete first transects"
    assert [item["id"] for item in tasks] == [task_id, subtask_id]
    assert tasks[0]["status"] == "To Do"
    assert tasks[0]["phase_id"] == phase_id
    assert tasks[0]["sprint_id"] == sprint_id
    assert tasks[0]["manual_estimate"] == 6.5
    assert tasks[1]["parent_task_id"] == task_id
    assert [item["id"] for item in allocations] == [allocation_id]
    assert allocations[0]["hours_per_week"] == 24
    assert allocations[0]["allocation_percent"] == 60
    assert allocations[0]["phase_id"] == phase_id

    with pytest.raises(KeyError):
        service.create_phase(
            project_id,
            "Cross organization",
            organization_id=f"other-{uuid4()}",
            actor_id=actor,
        )
    with pytest.raises(ValueError, match="cannot be before"):
        service.create_sprint(
            project_id,
            "Impossible sprint",
            organization_id=organization_id,
            actor_id=actor,
            start_date="2026-10-02",
            end_date="2026-10-01",
        )

    events = [item["event_type"] for item in service.activity(project_id)]
    assert events == [
        "project.created",
        "phase.created",
        "sprint.created",
        "task.created",
        "task.created",
        "allocation.updated",
    ]
