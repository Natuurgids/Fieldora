from __future__ import annotations

import os
from uuid import uuid4

import pytest

from natureai_next.server.postgres_project_capacity import (
    PostgresCapacityProjectManagementService,
)


def _connect_factory():
    dsn = os.environ.get("FIELDORA_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("FIELDORA_TEST_POSTGRES_DSN is not configured")
    psycopg = pytest.importorskip("psycopg")
    return lambda: psycopg.connect(dsn, connect_timeout=10)


@pytest.mark.integration
def test_managed_capacity_persists_schedule_absence_obligation_and_workload() -> None:
    service = PostgresCapacityProjectManagementService(_connect_factory())
    organization_id = f"org-capacity-{uuid4()}"
    actor = f"user-{uuid4()}"
    project_id = service.create_project(
        "Capacity Project",
        organization_id=organization_id,
        owner_id=actor,
        actor_id=actor,
    )

    templates = service.schedule_templates()
    assert {row["template_id"] for row in templates} >= {
        "40-hours",
        "36-hours",
        "32-hours",
        "40-32-alternating",
        "32-40-alternating",
    }
    assert service.project_members(project_id) == ({"user_id": actor, "role": "admin"},)

    assignment_id = service.assign_work_schedule(
        actor,
        "40-hours",
        "2026-09-14",
        reference_week="2026-09-14",
        actor_id=actor,
    )
    absence_id = service.add_absence(
        actor,
        "2026-09-14T08:00:00+00:00",
        "2026-09-14T12:00:00+00:00",
        "annual_leave",
        note="private leave detail",
        actor_id=actor,
    )
    obligation_id = service.add_organisational_obligation(
        actor,
        "2026-09-15T08:00:00+00:00",
        "2026-09-15T10:00:00+00:00",
        "organisation",
        "Team seminar",
        note="internal obligation detail",
        actor_id=actor,
    )
    allocation_id = service.create_allocation(
        project_id,
        actor,
        organization_id=organization_id,
        actor_id=actor,
        start_date="2026-09-14",
        end_date="2026-09-20",
        hours_per_week=20,
    )

    summary = service.capacity_summary(
        actor,
        "2026-09-14T00:00:00+00:00",
        "2026-09-21T00:00:00+00:00",
        project_id=project_id,
    )
    assert summary == {
        "scheduled_hours": 40.0,
        "absence_hours": 4.0,
        "organisational_hours": 2.0,
        "net_capacity_hours": 34.0,
        "allocated_hours": 20.0,
        "remaining_hours": 14.0,
    }

    with service._connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT privacy_level,status,note,created_by FROM hr_absences "
                "WHERE absence_id=%s",
                (absence_id,),
            )
            assert cursor.fetchone() == (
                "private",
                "approved",
                "private leave detail",
                actor,
            )
            cursor.execute(
                "SELECT event_type,record_id,actor_id FROM hr_capacity_activity "
                "WHERE user_id=%s ORDER BY activity_id",
                (actor,),
            )
            events = cursor.fetchall()
    assert events[-3:] == [
        ("schedule.assigned", assignment_id, actor),
        ("absence.registered", absence_id, actor),
        ("obligation.created", obligation_id, actor),
    ]
    assert allocation_id


@pytest.mark.integration
def test_managed_capacity_validates_ranges_and_keeps_private_detail_out_of_workload() -> None:
    service = PostgresCapacityProjectManagementService(_connect_factory())
    organization_id = f"org-capacity-private-{uuid4()}"
    actor = f"user-{uuid4()}"
    project_id = service.create_project(
        "Private Capacity Project",
        organization_id=organization_id,
        owner_id=actor,
        actor_id=actor,
    )

    with pytest.raises(ValueError, match="absence end must be after start"):
        service.add_absence(
            actor,
            "2026-09-14T12:00:00+00:00",
            "2026-09-14T08:00:00+00:00",
            "annual_leave",
            actor_id=actor,
        )
    with pytest.raises(ValueError, match="obligation end must be after start"):
        service.add_organisational_obligation(
            actor,
            "2026-09-15T10:00:00+00:00",
            "2026-09-15T08:00:00+00:00",
            "organisation",
            "Invalid obligation",
            actor_id=actor,
        )
    with pytest.raises(ValueError, match="unknown schedule template"):
        service.assign_work_schedule(
            actor,
            "missing-template",
            "2026-09-14",
            actor_id=actor,
        )

    workload = service.workload(project_id)
    assert len(workload) == 1
    row = workload[0]
    assert row["user_id"] == actor
    assert row["role"] == "admin"
    assert {
        "scheduled_hours",
        "absence_hours",
        "organisational_hours",
        "net_capacity_hours",
        "allocated_hours",
        "remaining_hours",
        "task_count",
        "open_estimate_hours",
        "actual_hours",
    } <= set(row)
    assert "privacy_level" not in row
    assert "note" not in row
    assert "absence_type" not in row
