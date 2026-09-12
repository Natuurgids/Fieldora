from __future__ import annotations

import json

from natureai_next.server.postgres_project_management import PostgresProjectManagementService


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        return None

    def execute(self, sql: str, params=None) -> None:
        self.last_sql = " ".join(sql.split())
        self.calls.append((self.last_sql, params))

    def fetchone(self):
        if "SELECT 1 FROM pm_projects" in self.last_sql:
            return (1,)
        if "SELECT status_id FROM pm_statuses" in self.last_sql:
            return ("status-1",)
        if "SELECT COALESCE(MAX(position),-1)+1 FROM pm_tasks" in self.last_sql:
            return (0,)
        raise AssertionError(f"unexpected fetchone for {self.last_sql}")


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        return None

    def cursor(self) -> _Cursor:
        return self._cursor


def test_web032_postgres_task_creation_persists_milestone_in_authoritative_table() -> None:
    cursor = _Cursor()
    connection = _Connection(cursor)
    service = PostgresProjectManagementService(lambda: connection)

    task_id = service.create_task(
        "project-1",
        "Field complete",
        organization_id="org-1",
        actor_id="user-1",
        milestone=True,
    )

    task_insert = next(
        params for sql, params in cursor.calls if "INSERT INTO pm_tasks(" in sql
    )
    assert task_insert[0] == task_id
    assert task_insert[1] == "project-1"
    assert task_insert[3] == "Field complete"
    assert task_insert[11] is True

    activity_insert = next(
        params for sql, params in cursor.calls if "INSERT INTO pm_activity(" in sql
    )
    details = json.loads(activity_insert[4])
    assert details == {
        "task_id": task_id,
        "title": "Field complete",
        "milestone": True,
    }
