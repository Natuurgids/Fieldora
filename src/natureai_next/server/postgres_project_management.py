"""PostgreSQL Project Management adapter for managed Fieldora.

The managed adapter preserves the authoritative Project Management creation and
lifecycle invariants while adding the organization boundary required by a shared
server. Browser/API adapters are transport and authorization layers only.
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
    """Managed-server Project service with organization-scoped lifecycle updates."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("fieldora_project_management_schema_v2",),
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
                cursor.execute(
                    """
                    INSERT INTO pm_activity(
                        project_id,task_id,actor_id,event_type,details_json,created_at_us
                    ) VALUES(%s,NULL,%s,'project.created',%s,%s)
                    """,
                    (project_id, actor_id, json.dumps({"name": name}), now),
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
                cursor.execute(
                    """
                    INSERT INTO pm_activity(
                        project_id,task_id,actor_id,event_type,details_json,created_at_us
                    ) VALUES(%s,NULL,%s,'project.updated',%s,%s)
                    """,
                    (project_id, actor_id, json.dumps(details), revision),
                )
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
                cursor.execute(
                    """
                    INSERT INTO pm_activity(
                        project_id,task_id,actor_id,event_type,details_json,created_at_us
                    ) VALUES(%s,NULL,%s,%s,%s,%s)
                    """,
                    (
                        project_id,
                        actor_id,
                        event_type,
                        json.dumps({"status": normalized}),
                        revision,
                    ),
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
