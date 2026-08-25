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
