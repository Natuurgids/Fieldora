"""PostgreSQL Project Management adapter for managed Fieldora.

The managed adapter preserves the authoritative Project Management creation,
lifecycle and child-work invariants while adding the organization boundary required
by a shared server. Browser/API adapters are transport and authorization layers only.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ManagedProjectSummary:
    project_id: str
    organization_id: str
    name: str
    status: str
    owner_id: str
    start_date: str
    due_date: str
    budget: float
    currency: str
    description: str = ""
    revision: int = 0


def _now_us() -> int:
    return time.time_ns() // 1_000


def _next_revision(previous: int) -> int:
    return max(_now_us(), int(previous) + 1)


def _id() -> str:
    return str(uuid4())


def _validate_date(value: str, label: str) -> None:
    if value:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{label} must use YYYY-MM-DD") from exc


def _validate_project_dates(start_date: str, due_date: str) -> None:
    _validate_date(start_date, "project start date")
    _validate_date(due_date, "project due date")
    if start_date and due_date and due_date < start_date:
        raise ValueError("project due date cannot be before its start date")


class PostgresProjectManagementService:
    """Managed-server Project service with organization-scoped governed work."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("fieldora_project_management_schema_v3",),
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pm_projects(
                        project_id TEXT PRIMARY KEY,
                        organization_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'active',
                        owner_id TEXT NOT NULL DEFAULT '',
                        start_date TEXT NOT NULL DEFAULT '',
                        due_date TEXT NOT NULL DEFAULT '',
                        budget DOUBLE PRECISION NOT NULL DEFAULT 0,
                        currency TEXT NOT NULL DEFAULT 'EUR',
                        template_id TEXT,
                        client_name TEXT NOT NULL DEFAULT '',
                        created_at_us BIGINT NOT NULL,
                        updated_at_us BIGINT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    "ALTER TABLE pm_projects ADD COLUMN IF NOT EXISTS organization_id TEXT"
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pm_statuses(
                        status_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                            ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        category TEXT NOT NULL,
                        color TEXT NOT NULL,
                        display_order INTEGER NOT NULL,
                        wip_limit INTEGER,
                        UNIQUE(project_id,name)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pm_project_members(
                        project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                            ON DELETE CASCADE,
                        user_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        PRIMARY KEY(project_id,user_id)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pm_phases(
                        phase_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                            ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        planned_budget DOUBLE PRECISION NOT NULL DEFAULT 0,
                        realized_budget DOUBLE PRECISION NOT NULL DEFAULT 0,
                        display_order INTEGER NOT NULL DEFAULT 0,
                        created_by TEXT NOT NULL,
                        created_at_us BIGINT NOT NULL,
                        updated_at_us BIGINT NOT NULL,
                        UNIQUE(project_id,name)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pm_sprints(
                        sprint_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                            ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        start_date TEXT NOT NULL DEFAULT '',
                        end_date TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'planned',
                        goal TEXT NOT NULL DEFAULT '',
                        created_by TEXT NOT NULL,
                        created_at_us BIGINT NOT NULL,
                        updated_at_us BIGINT NOT NULL,
                        UNIQUE(project_id,name)
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pm_tasks(
                        task_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                            ON DELETE CASCADE,
                        parent_task_id TEXT REFERENCES pm_tasks(task_id) ON DELETE CASCADE,
                        title TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        status_id TEXT NOT NULL REFERENCES pm_statuses(status_id),
                        owner_id TEXT NOT NULL DEFAULT '',
                        priority TEXT NOT NULL DEFAULT 'normal',
                        start_date TEXT NOT NULL DEFAULT '',
                        due_date TEXT NOT NULL DEFAULT '',
                        estimate_hours DOUBLE PRECISION NOT NULL DEFAULT 0,
                        budget DOUBLE PRECISION NOT NULL DEFAULT 0,
                        progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
                        recurrence TEXT NOT NULL DEFAULT 'none',
                        recurrence_end TEXT NOT NULL DEFAULT '',
                        milestone BOOLEAN NOT NULL DEFAULT FALSE,
                        sprint TEXT NOT NULL DEFAULT '',
                        position INTEGER NOT NULL DEFAULT 0,
                        phase_id TEXT REFERENCES pm_phases(phase_id) ON DELETE SET NULL,
                        sprint_id TEXT REFERENCES pm_sprints(sprint_id) ON DELETE SET NULL,
                        realized_hours DOUBLE PRECISION NOT NULL DEFAULT 0,
                        created_by TEXT NOT NULL,
                        created_at_us BIGINT NOT NULL,
                        updated_at_us BIGINT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hr_project_allocations(
                        allocation_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                            ON DELETE CASCADE,
                        start_date TEXT NOT NULL,
                        end_date TEXT NOT NULL DEFAULT '',
                        hours_per_week DOUBLE PRECISION NOT NULL DEFAULT 0,
                        allocation_percent DOUBLE PRECISION NOT NULL DEFAULT 0,
                        role TEXT NOT NULL DEFAULT '',
                        phase_id TEXT REFERENCES pm_phases(phase_id) ON DELETE SET NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        created_by TEXT NOT NULL,
                        created_at_us BIGINT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pm_activity(
                        activity_id BIGSERIAL PRIMARY KEY,
                        project_id TEXT NOT NULL REFERENCES pm_projects(project_id)
                            ON DELETE CASCADE,
                        task_id TEXT,
                        actor_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        details_json TEXT NOT NULL DEFAULT '{}',
                        created_at_us BIGINT NOT NULL
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_pm_projects_org_updated_pg "
                    "ON pm_projects(organization_id,updated_at_us DESC)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_pm_activity_project_pg "
                    "ON pm_activity(project_id,created_at_us)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_pm_tasks_project_pg "
                    "ON pm_tasks(project_id,status_id,position,due_date)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_pm_phases_project_pg "
                    "ON pm_phases(project_id,display_order,name)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_pm_sprints_project_pg "
                    "ON pm_sprints(project_id,start_date,name)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_hr_allocations_project_pg "
                    "ON hr_project_allocations(project_id,user_id,start_date)"
                )

    @staticmethod
    def _require_project(cursor, project_id: str, organization_id: str) -> None:
        cursor.execute(
            "SELECT 1 FROM pm_projects WHERE project_id=%s AND organization_id=%s",
            (project_id, organization_id),
        )
        if cursor.fetchone() is None:
            raise KeyError(project_id)

    @staticmethod
    def _require_child(cursor, table: str, id_column: str, child_id: str, project_id: str) -> None:
        if not child_id:
            return
        allowed = {
            ("pm_phases", "phase_id"),
            ("pm_sprints", "sprint_id"),
            ("pm_tasks", "task_id"),
        }
        if (table, id_column) not in allowed:
            raise ValueError("invalid Project child reference")
        cursor.execute(
            f"SELECT 1 FROM {table} WHERE {id_column}=%s AND project_id=%s",  # noqa: S608
            (child_id, project_id),
        )
        if cursor.fetchone() is None:
            raise ValueError("Project child reference belongs to another Project or does not exist")

    @staticmethod
    def _event(cursor, project_id: str, actor_id: str, event_type: str, details: dict[str, object], *, task_id: str | None = None) -> None:
        cursor.execute(
            """
            INSERT INTO pm_activity(
                project_id,task_id,actor_id,event_type,details_json,created_at_us
            ) VALUES(%s,%s,%s,%s,%s,%s)
            """,
            (project_id, task_id, actor_id, event_type, json.dumps(details), _now_us()),
        )

    def create_project(
        self,
        name: str,
        *,
        organization_id: str,
        owner_id: str,
        actor_id: str,
        start_date: str = "",
        due_date: str = "",
        description: str = "",
        budget: float = 0,
        currency: str = "EUR",
        template_id: str | None = None,
    ) -> str:
        if not organization_id.strip():
            raise ValueError("organization is required")
        if not name.strip():
            raise ValueError("project name is required")
        _validate_project_dates(start_date, due_date)
        if template_id:
            raise ValueError(
                "project templates are not yet available in the managed PostgreSQL adapter"
            )
        project_id = _id()
        now = _now_us()
        statuses = (
            ("To Do", "todo", "#6b7280"),
            ("In Progress", "active", "#2563eb"),
            ("QA", "review", "#7c3aed"),
            ("Blocked", "blocked", "#dc2626"),
            ("Done", "done", "#16a34a"),
        )
        member_id = owner_id.strip() or actor_id
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO pm_projects(
                        project_id,organization_id,name,description,status,owner_id,
                        start_date,due_date,budget,currency,template_id,client_name,
                        created_at_us,updated_at_us
                    ) VALUES(%s,%s,%s,%s,'active',%s,%s,%s,%s,%s,%s,'',%s,%s)
                    """,
                    (
                        project_id,
                        organization_id.strip(),
                        name.strip(),
                        description.strip(),
                        owner_id.strip(),
                        start_date,
                        due_date,
                        float(budget),
                        currency.strip() or "EUR",
                        template_id,
                        now,
                        now,
                    ),
                )
                for order, (status_name, category, color) in enumerate(statuses):
                    cursor.execute(
                        """
                        INSERT INTO pm_statuses(
                            status_id,project_id,name,category,color,display_order,wip_limit
                        ) VALUES(%s,%s,%s,%s,%s,%s,NULL)
                        """,
                        (_id(), project_id, status_name, category, color, order),
                    )
                cursor.execute(
                    "INSERT INTO pm_project_members(project_id,user_id,role) "
                    "VALUES(%s,%s,'admin')",
                    (project_id, member_id),
                )
                self._event(
                    cursor,
                    project_id,
                    actor_id,
                    "project.created",
                    {"name": name},
                )
        return project_id

    def projects(self, organization_id: str) -> tuple[ManagedProjectSummary, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT project_id,organization_id,name,status,owner_id,start_date,
                           due_date,budget,currency,description,updated_at_us
                    FROM pm_projects WHERE organization_id=%s
                    ORDER BY updated_at_us DESC,project_id
                    """,
                    (organization_id,),
                )
                rows = cursor.fetchall()
        return tuple(
            ManagedProjectSummary(
                str(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                str(row[4]),
                str(row[5]),
                str(row[6]),
                float(row[7]),
                str(row[8]),
                str(row[9]),
                int(row[10]),
            )
            for row in rows
        )

    def create_phase(
        self,
        project_id: str,
        name: str,
        *,
        organization_id: str,
        actor_id: str,
        description: str = "",
        planned_budget: float = 0,
        realized_budget: float = 0,
    ) -> str:
        if not name.strip():
            raise ValueError("phase name is required")
        phase_id = _id()
        now = _now_us()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_project(cursor, project_id, organization_id)
                cursor.execute(
                    "SELECT COALESCE(MAX(display_order),-1)+1 FROM pm_phases WHERE project_id=%s",
                    (project_id,),
                )
                display_order = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    INSERT INTO pm_phases(
                        phase_id,project_id,name,description,planned_budget,realized_budget,
                        display_order,created_by,created_at_us,updated_at_us
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        phase_id,
                        project_id,
                        name.strip(),
                        description.strip(),
                        float(planned_budget),
                        float(realized_budget),
                        display_order,
                        actor_id,
                        now,
                        now,
                    ),
                )
                self._event(
                    cursor,
                    project_id,
                    actor_id,
                    "phase.created",
                    {"phase_id": phase_id, "name": name.strip()},
                )
        return phase_id

    def phases(self, organization_id: str) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ph.phase_id,ph.project_id,ph.name,ph.description,
                           ph.planned_budget,ph.realized_budget,ph.display_order
                    FROM pm_phases ph
                    JOIN pm_projects p ON p.project_id=ph.project_id
                    WHERE p.organization_id=%s
                    ORDER BY ph.project_id,ph.display_order,ph.name,ph.phase_id
                    """,
                    (organization_id,),
                )
                rows = cursor.fetchall()
        return tuple(
            {
                "id": str(row[0]),
                "project_id": str(row[1]),
                "name": str(row[2]),
                "description": str(row[3]),
                "planned_budget": float(row[4]),
                "realized_budget": float(row[5]),
                "display_order": int(row[6]),
            }
            for row in rows
        )

    def create_sprint(
        self,
        project_id: str,
        name: str,
        *,
        organization_id: str,
        actor_id: str,
        start_date: str = "",
        end_date: str = "",
        status: str = "planned",
        goal: str = "",
    ) -> str:
        if not name.strip():
            raise ValueError("sprint name is required")
        _validate_date(start_date, "sprint start date")
        _validate_date(end_date, "sprint end date")
        if start_date and end_date and end_date < start_date:
            raise ValueError("sprint end date cannot be before its start date")
        normalized_status = status.strip().lower() or "planned"
        if normalized_status not in {"planned", "active", "completed", "cancelled"}:
            raise ValueError("invalid sprint status")
        sprint_id = _id()
        now = _now_us()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_project(cursor, project_id, organization_id)
                cursor.execute(
                    """
                    INSERT INTO pm_sprints(
                        sprint_id,project_id,name,start_date,end_date,status,goal,created_by,
                        created_at_us,updated_at_us
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        sprint_id,
                        project_id,
                        name.strip(),
                        start_date,
                        end_date,
                        normalized_status,
                        goal.strip(),
                        actor_id,
                        now,
                        now,
                    ),
                )
                self._event(
                    cursor,
                    project_id,
                    actor_id,
                    "sprint.created",
                    {"sprint_id": sprint_id, "name": name.strip()},
                )
        return sprint_id

    def sprints(self, organization_id: str) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT s.sprint_id,s.project_id,s.name,s.start_date,s.end_date,s.status,s.goal
                    FROM pm_sprints s
                    JOIN pm_projects p ON p.project_id=s.project_id
                    WHERE p.organization_id=%s
                    ORDER BY s.project_id,s.start_date,s.name,s.sprint_id
                    """,
                    (organization_id,),
                )
                rows = cursor.fetchall()
        return tuple(
            {
                "id": str(row[0]),
                "project_id": str(row[1]),
                "name": str(row[2]),
                "start_date": str(row[3]),
                "end_date": str(row[4]),
                "status": str(row[5]),
                "goal": str(row[6]),
            }
            for row in rows
        )

    def create_task(
        self,
        project_id: str,
        title: str,
        *,
        organization_id: str,
        actor_id: str,
        parent_task_id: str | None = None,
        phase_id: str | None = None,
        sprint_id: str | None = None,
        owner_id: str = "",
        description: str = "",
        priority: str = "normal",
        start_date: str = "",
        due_date: str = "",
        estimate_hours: float = 0,
        realized_hours: float = 0,
    ) -> str:
        if not title.strip():
            raise ValueError("task title is required")
        _validate_date(start_date, "task start date")
        _validate_date(due_date, "task due date")
        if start_date and due_date and due_date < start_date:
            raise ValueError("task due date cannot be before its start date")
        if float(estimate_hours) < 0 or float(realized_hours) < 0:
            raise ValueError("task hours cannot be negative")
        task_id = _id()
        now = _now_us()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_project(cursor, project_id, organization_id)
                self._require_child(cursor, "pm_phases", "phase_id", phase_id or "", project_id)
                self._require_child(cursor, "pm_sprints", "sprint_id", sprint_id or "", project_id)
                self._require_child(
                    cursor, "pm_tasks", "task_id", parent_task_id or "", project_id
                )
                cursor.execute(
                    """
                    SELECT status_id FROM pm_statuses
                    WHERE project_id=%s ORDER BY display_order,status_id LIMIT 1
                    """,
                    (project_id,),
                )
                status_row = cursor.fetchone()
                if status_row is None:
                    raise ValueError("Project has no workflow status")
                cursor.execute(
                    "SELECT COALESCE(MAX(position),-1)+1 FROM pm_tasks WHERE project_id=%s",
                    (project_id,),
                )
                position = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    INSERT INTO pm_tasks(
                        task_id,project_id,parent_task_id,title,description,status_id,owner_id,
                        priority,start_date,due_date,estimate_hours,budget,progress,recurrence,
                        recurrence_end,milestone,sprint,position,phase_id,sprint_id,realized_hours,
                        created_by,created_at_us,updated_at_us
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,'none','',FALSE,'',%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        task_id,
                        project_id,
                        parent_task_id or None,
                        title.strip(),
                        description.strip(),
                        str(status_row[0]),
                        owner_id.strip(),
                        priority.strip().lower() or "normal",
                        start_date,
                        due_date,
                        float(estimate_hours),
                        position,
                        phase_id or None,
                        sprint_id or None,
                        float(realized_hours),
                        actor_id,
                        now,
                        now,
                    ),
                )
                self._event(
                    cursor,
                    project_id,
                    actor_id,
                    "task.created",
                    {"task_id": task_id, "title": title.strip()},
                    task_id=task_id,
                )
        return task_id

    def tasks(self, organization_id: str) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.task_id,t.project_id,t.parent_task_id,t.title,t.description,
                           s.name,t.owner_id,t.priority,t.start_date,t.due_date,t.estimate_hours,
                           t.realized_hours,t.phase_id,t.sprint_id,t.position
                    FROM pm_tasks t
                    JOIN pm_projects p ON p.project_id=t.project_id
                    JOIN pm_statuses s ON s.status_id=t.status_id
                    WHERE p.organization_id=%s
                    ORDER BY t.project_id,t.position,t.created_at_us,t.task_id
                    """,
                    (organization_id,),
                )
                rows = cursor.fetchall()
        return tuple(
            {
                "id": str(row[0]),
                "project_id": str(row[1]),
                "parent_task_id": "" if row[2] is None else str(row[2]),
                "name": str(row[3]),
                "title": str(row[3]),
                "description": str(row[4]),
                "status": str(row[5]),
                "assignee_id": str(row[6]),
                "priority": str(row[7]),
                "start_date": str(row[8]),
                "due_date": str(row[9]),
                "manual_estimate": float(row[10]),
                "realized": float(row[11]),
                "phase_id": "" if row[12] is None else str(row[12]),
                "sprint_id": "" if row[13] is None else str(row[13]),
                "position": int(row[14]),
            }
            for row in rows
        )

    def create_allocation(
        self,
        project_id: str,
        user_id: str,
        *,
        organization_id: str,
        actor_id: str,
        start_date: str,
        end_date: str = "",
        hours_per_week: float = 0,
        allocation_percent: float = 0,
        role: str = "",
        phase_id: str | None = None,
    ) -> str:
        if not user_id.strip():
            raise ValueError("allocation user is required")
        if not start_date:
            raise ValueError("allocation start date is required")
        _validate_date(start_date, "allocation start date")
        _validate_date(end_date, "allocation end date")
        if end_date and end_date < start_date:
            raise ValueError("allocation end date cannot be before its start date")
        if float(hours_per_week) < 0 or float(allocation_percent) < 0:
            raise ValueError("allocation cannot be negative")
        allocation_id = _id()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_project(cursor, project_id, organization_id)
                self._require_child(cursor, "pm_phases", "phase_id", phase_id or "", project_id)
                cursor.execute(
                    """
                    INSERT INTO hr_project_allocations(
                        allocation_id,user_id,project_id,start_date,end_date,hours_per_week,
                        allocation_percent,role,phase_id,status,created_by,created_at_us
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'active',%s,%s)
                    """,
                    (
                        allocation_id,
                        user_id.strip(),
                        project_id,
                        start_date,
                        end_date,
                        float(hours_per_week),
                        float(allocation_percent),
                        role.strip(),
                        phase_id or None,
                        actor_id,
                        _now_us(),
                    ),
                )
                self._event(
                    cursor,
                    project_id,
                    actor_id,
                    "allocation.updated",
                    {
                        "allocation_id": allocation_id,
                        "user": user_id.strip(),
                        "hours_per_week": float(hours_per_week),
                        "percent": float(allocation_percent),
                    },
                )
        return allocation_id

    def allocations(self, organization_id: str) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT a.allocation_id,a.user_id,a.project_id,a.start_date,a.end_date,
                           a.hours_per_week,a.allocation_percent,a.role,a.phase_id,a.status
                    FROM hr_project_allocations a
                    JOIN pm_projects p ON p.project_id=a.project_id
                    WHERE p.organization_id=%s
                    ORDER BY a.project_id,a.start_date,a.user_id,a.allocation_id
                    """,
                    (organization_id,),
                )
                rows = cursor.fetchall()
        return tuple(
            {
                "id": str(row[0]),
                "user_id": str(row[1]),
                "project_id": str(row[2]),
                "start_date": str(row[3]),
                "end_date": str(row[4]),
                "hours_per_week": float(row[5]),
                "allocation_percent": float(row[6]),
                "role": str(row[7]),
                "phase_id": "" if row[8] is None else str(row[8]),
                "status": str(row[9]),
            }
            for row in rows
        )

    def update_project(
        self,
        project_id: str,
        *,
        organization_id: str,
        actor_id: str,
        expected_revision: int,
        name: str | None = None,
        description: str | None = None,
        start_date: str | None = None,
        due_date: str | None = None,
        budget: float | None = None,
        currency: str | None = None,
    ) -> int:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT name,description,start_date,due_date,budget,currency,status,
                           updated_at_us
                    FROM pm_projects
                    WHERE project_id=%s AND organization_id=%s
                    FOR UPDATE
                    """,
                    (project_id, organization_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(project_id)
                current_revision = int(row[7])
                if int(expected_revision) != current_revision:
                    raise ValueError("project revision conflict")
                next_name = str(row[0]) if name is None else str(name).strip()
                next_description = str(row[1]) if description is None else str(description).strip()
                next_start = str(row[2]) if start_date is None else str(start_date)
                next_due = str(row[3]) if due_date is None else str(due_date)
                next_budget = float(row[4]) if budget is None else float(budget)
                next_currency = str(row[5]) if currency is None else str(currency).strip() or "EUR"
                if not next_name:
                    raise ValueError("project name is required")
                _validate_project_dates(next_start, next_due)
                revision = _next_revision(current_revision)
                cursor.execute(
                    """
                    UPDATE pm_projects
                    SET name=%s,description=%s,start_date=%s,due_date=%s,budget=%s,
                        currency=%s,updated_at_us=%s
                    WHERE project_id=%s AND organization_id=%s
                    """,
                    (
                        next_name,
                        next_description,
                        next_start,
                        next_due,
                        next_budget,
                        next_currency,
                        revision,
                        project_id,
                        organization_id,
                    ),
                )
                details = {
                    "name": next_name,
                    "description": next_description,
                    "start_date": next_start,
                    "due_date": next_due,
                    "budget": next_budget,
                    "currency": next_currency,
                }
                self._event(cursor, project_id, actor_id, "project.updated", details)
        return revision

    def set_project_status(
        self,
        project_id: str,
        status: str,
        *,
        organization_id: str,
        actor_id: str,
        expected_revision: int,
    ) -> int:
        normalized = status.strip().lower()
        if normalized not in {"active", "archived", "cancelled"}:
            raise ValueError("invalid project status")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT status,updated_at_us FROM pm_projects
                    WHERE project_id=%s AND organization_id=%s
                    FOR UPDATE
                    """,
                    (project_id, organization_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(project_id)
                current_revision = int(row[1])
                if int(expected_revision) != current_revision:
                    raise ValueError("project revision conflict")
                revision = _next_revision(current_revision)
                cursor.execute(
                    """
                    UPDATE pm_projects SET status=%s,updated_at_us=%s
                    WHERE project_id=%s AND organization_id=%s
                    """,
                    (normalized, revision, project_id, organization_id),
                )
                event_type = "project.archived" if normalized == "archived" else "project.status_changed"
                self._event(
                    cursor,
                    project_id,
                    actor_id,
                    event_type,
                    {"status": normalized},
                )
        return revision

    def archive_project(
        self,
        project_id: str,
        *,
        organization_id: str,
        actor_id: str,
        expected_revision: int,
    ) -> int:
        return self.set_project_status(
            project_id,
            "archived",
            organization_id=organization_id,
            actor_id=actor_id,
            expected_revision=expected_revision,
        )

    def statuses(self, project_id: str) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status_id,name,category,color,display_order,wip_limit "
                    "FROM pm_statuses WHERE project_id=%s ORDER BY display_order,status_id",
                    (project_id,),
                )
                rows = cursor.fetchall()
        return tuple(
            {
                "status_id": str(row[0]),
                "name": str(row[1]),
                "category": str(row[2]),
                "color": str(row[3]),
                "display_order": int(row[4]),
                "wip_limit": row[5],
            }
            for row in rows
        )

    def member_role(self, project_id: str, user_id: str) -> str | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT role FROM pm_project_members WHERE project_id=%s AND user_id=%s",
                    (project_id, user_id),
                )
                row = cursor.fetchone()
        return None if row is None else str(row[0])

    def activity(self, project_id: str) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT actor_id,event_type,details_json,created_at_us "
                    "FROM pm_activity WHERE project_id=%s ORDER BY activity_id",
                    (project_id,),
                )
                rows = cursor.fetchall()
        return tuple(
            {
                "actor_id": str(row[0]),
                "event_type": str(row[1]),
                "details": json.loads(str(row[2])),
                "created_at_us": int(row[3]),
            }
            for row in rows
        )
