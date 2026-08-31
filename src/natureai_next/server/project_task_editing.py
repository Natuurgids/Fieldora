"""Uniform task-detail/edit operations for local and managed Project services.

The desktop SQLite service already owns task mutation semantics, while the managed
PostgreSQL adapter exposes Project child creation/listing but not yet a task-update
method. This facade keeps the browser transport storage-agnostic and delegates local
mutations unchanged while providing the equivalent managed persistence boundary.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from natureai_next.application.project_task_detail import ProjectTaskDetailQuery

_EDITABLE_FIELDS = frozenset(
    {
        "title",
        "description",
        "status_id",
        "owner_id",
        "priority",
        "start_date",
        "due_date",
        "estimate_hours",
        "budget",
        "progress",
        "recurrence",
        "recurrence_end",
        "milestone",
        "phase_id",
        "sprint_id",
        "realized_hours",
    }
)


def _validate_date(value: object, label: str) -> str:
    text = str(value or "").strip()
    if text:
        try:
            date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{label} must use YYYY-MM-DD") from exc
    return text


class ProjectTaskEditingFacade:
    """Expose one task-detail/update contract across supported Project backends."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    @property
    def _is_local_sqlite(self) -> bool:
        return getattr(self._delegate, "database_path", None) is not None

    def task_detail(
        self,
        project_id: str,
        task_id: str,
        *,
        organization_id: str = "",
    ) -> dict[str, object] | None:
        database_path = getattr(self._delegate, "database_path", None)
        if database_path is not None:
            return ProjectTaskDetailQuery(database_path).get(project_id, task_id)
        connect = getattr(self._delegate, "_connect", None)
        if not callable(connect):
            return None
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.task_id,t.project_id,t.parent_task_id,t.title,t.description,
                           t.status_id,s.name,s.category,t.owner_id,t.priority,t.start_date,
                           t.due_date,t.estimate_hours,t.budget,t.progress,t.recurrence,
                           t.recurrence_end,t.milestone,t.sprint,t.position,t.phase_id,
                           t.sprint_id,t.realized_hours
                    FROM pm_tasks t
                    JOIN pm_statuses s ON s.status_id=t.status_id
                    JOIN pm_projects p ON p.project_id=t.project_id
                    WHERE t.project_id=%s AND t.task_id=%s
                      AND (%s='' OR p.organization_id=%s)
                    """,
                    (project_id, task_id, organization_id, organization_id),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return {
            "id": str(row[0]),
            "task_id": str(row[0]),
            "project_id": str(row[1]),
            "parent_task_id": None if row[2] is None else str(row[2]),
            "title": str(row[3]),
            "description": str(row[4]),
            "status_id": str(row[5]),
            "status_name": str(row[6]),
            "status_category": str(row[7]),
            "owner_id": str(row[8]),
            "priority": str(row[9]),
            "start_date": str(row[10]),
            "due_date": str(row[11]),
            "estimate_hours": float(row[12]),
            "budget": float(row[13]),
            "progress": int(row[14]),
            "recurrence": str(row[15]),
            "recurrence_end": str(row[16]),
            "milestone": bool(row[17]),
            "sprint": str(row[18]),
            "position": int(row[19]),
            "phase_id": None if row[20] is None else str(row[20]),
            "sprint_id": None if row[21] is None else str(row[21]),
            "realized_hours": float(row[22]),
        }

    def phases(self, scope_id: str) -> tuple[dict[str, object], ...]:
        """Accept the local project scope or the managed organization/project scope."""
        if self._is_local_sqlite:
            return tuple(dict(item) for item in self._delegate.phases(scope_id))
        organization_rows = tuple(dict(item) for item in self._delegate.phases(scope_id))
        if organization_rows or tuple(self._delegate.projects(scope_id)):
            return organization_rows
        return self._managed_children("pm_phases", "phase_id", scope_id)

    def sprints(self, scope_id: str) -> tuple[dict[str, object], ...]:
        """Accept the local project scope or the managed organization/project scope."""
        if self._is_local_sqlite:
            return tuple(dict(item) for item in self._delegate.sprints(scope_id))
        organization_rows = tuple(dict(item) for item in self._delegate.sprints(scope_id))
        if organization_rows or tuple(self._delegate.projects(scope_id)):
            return organization_rows
        return self._managed_children("pm_sprints", "sprint_id", scope_id)

    def _managed_children(
        self, table: str, id_column: str, project_id: str
    ) -> tuple[dict[str, object], ...]:
        allowed = {
            ("pm_phases", "phase_id"),
            ("pm_sprints", "sprint_id"),
        }
        if (table, id_column) not in allowed:
            raise ValueError("unsupported Project child table")
        connect = getattr(self._delegate, "_connect", None)
        if not callable(connect):
            return ()
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT {id_column},project_id,name FROM {table} WHERE project_id=%s",  # noqa: S608
                    (project_id,),
                )
                rows = cursor.fetchall()
        return tuple(
            {"id": str(row[0]), id_column: str(row[0]), "project_id": str(row[1]), "name": str(row[2])}
            for row in rows
        )

    def status_ids(self, project_id: str) -> set[str]:
        return {
            str(item.get("status_id") or item.get("id") or "")
            for item in self._delegate.statuses(project_id)
        }

    def phase_ids(self, project_id: str) -> set[str]:
        return {
            str(item.get("phase_id") or item.get("id") or "")
            for item in self.phases(project_id)
            if str(item.get("project_id") or project_id) == project_id
        }

    def sprint_ids(self, project_id: str) -> set[str]:
        return {
            str(item.get("sprint_id") or item.get("id") or "")
            for item in self.sprints(project_id)
            if str(item.get("project_id") or project_id) == project_id
        }

    def update_task(
        self,
        task_id: str,
        *,
        actor_id: str,
        organization_id: str = "",
        **changes: object,
    ) -> None:
        values = {key: value for key, value in changes.items() if key in _EDITABLE_FIELDS}
        if not values:
            return
        if self._is_local_sqlite:
            self._delegate.update_task(task_id, actor_id=actor_id, **values)
            return
        connect = getattr(self._delegate, "_connect", None)
        event = getattr(self._delegate, "_event", None)
        if not callable(connect) or not callable(event):
            raise RuntimeError("Project service does not support task editing")
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.project_id,t.owner_id,t.status_id
                    FROM pm_tasks t JOIN pm_projects p ON p.project_id=t.project_id
                    WHERE t.task_id=%s AND (%s='' OR p.organization_id=%s)
                    FOR UPDATE
                    """,
                    (task_id, organization_id, organization_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(task_id)
                project_id = str(row[0])
                self._validate_managed_values(cursor, project_id, task_id, values)
                assignments = ",".join(f"{key}=%s" for key in values)
                cursor.execute(
                    f"UPDATE pm_tasks SET {assignments},updated_at_us=%s WHERE task_id=%s",  # noqa: S608
                    (*values.values(), self._now_us(), task_id),
                )
                event(
                    cursor,
                    project_id,
                    actor_id,
                    "task.updated",
                    dict(values),
                    task_id=task_id,
                )

    def _now_us(self) -> int:
        module = __import__(self._managed_module_name(), fromlist=["_now_us"])
        return int(module._now_us())

    def _managed_module_name(self) -> str:
        target = self._delegate
        if hasattr(target, "_delegate"):
            target = target._delegate
        return target.__class__.__module__

    @staticmethod
    def _validate_managed_values(
        cursor: Any,
        project_id: str,
        task_id: str,
        values: dict[str, object],
    ) -> None:
        if "title" in values and not str(values["title"]).strip():
            raise ValueError("task title is required")
        start = _validate_date(values.get("start_date", ""), "task start date")
        due = _validate_date(values.get("due_date", ""), "task due date")
        _validate_date(values.get("recurrence_end", ""), "recurrence end date")
        if start and due and due < start:
            raise ValueError("due date cannot be before start date")
        if "status_id" in values:
            cursor.execute(
                "SELECT category,wip_limit FROM pm_statuses WHERE status_id=%s AND project_id=%s",
                (values["status_id"], project_id),
            )
            status = cursor.fetchone()
            if status is None:
                raise ValueError("status does not belong to project")
            if status[1] is not None:
                cursor.execute(
                    "SELECT COUNT(*) FROM pm_tasks WHERE status_id=%s AND task_id<>%s",
                    (values["status_id"], task_id),
                )
                if int(cursor.fetchone()[0]) >= int(status[1]):
                    raise ValueError("workflow status WIP limit has been reached")
        for column, table in (("phase_id", "pm_phases"), ("sprint_id", "pm_sprints")):
            child_id = values.get(column)
            if child_id:
                cursor.execute(
                    f"SELECT 1 FROM {table} WHERE {column}=%s AND project_id=%s",  # noqa: S608
                    (child_id, project_id),
                )
                if cursor.fetchone() is None:
                    label = column.removesuffix("_id")
                    raise ValueError(f"{label} does not belong to project")


def wrap_project_task_editing(service: Any) -> Any:
    if service is None or isinstance(service, ProjectTaskEditingFacade):
        return service
    return ProjectTaskEditingFacade(service)
