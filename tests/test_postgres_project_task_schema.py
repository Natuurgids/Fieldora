from __future__ import annotations

from typing import Any

from natureai_next.server.postgres_project_task_schema import (
    ensure_managed_project_task_schema,
)


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.calls.append((" ".join(sql.split()), params))


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> _Cursor:
        return self._cursor


class _ManagedProjectService:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def _connect(self) -> _Connection:
        return _Connection(self._cursor)


class _LocalProjectService:
    database_path = "projects.sqlite3"

    @staticmethod
    def _connect() -> None:
        raise AssertionError("local Project schema must remain service-owned")


def test_managed_task_dependency_schema_is_provisioned_idempotently() -> None:
    cursor = _Cursor()

    ensure_managed_project_task_schema(_ManagedProjectService(cursor))

    statements = [sql for sql, _params in cursor.calls]
    assert statements[0] == "SELECT pg_advisory_xact_lock(hashtext(%s))"
    assert cursor.calls[0][1] == ("fieldora_project_task_dependency_schema_v1",)
    ddl = statements[1]
    assert "CREATE TABLE IF NOT EXISTS pm_task_dependencies" in ddl
    assert "task_id TEXT NOT NULL REFERENCES pm_tasks(task_id) ON DELETE CASCADE" in ddl
    assert "depends_on_task_id TEXT NOT NULL REFERENCES pm_tasks(task_id) ON DELETE CASCADE" in ddl
    assert "dependency_type TEXT NOT NULL DEFAULT 'finish_to_start'" in ddl
    assert "PRIMARY KEY(task_id,depends_on_task_id)" in ddl
    assert "CHECK(task_id<>depends_on_task_id)" in ddl


def test_local_project_schema_is_not_touched() -> None:
    ensure_managed_project_task_schema(_LocalProjectService())
