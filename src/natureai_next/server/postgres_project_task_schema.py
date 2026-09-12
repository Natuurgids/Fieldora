"""Managed PostgreSQL schema compatibility for Project task dependencies."""

from __future__ import annotations

from typing import Any


def ensure_managed_project_task_schema(project_management: Any) -> None:
    """Provision dependency storage required by managed task parity.

    Local SQLite Project services own their schema internally. Managed PostgreSQL
    installations created before dependency-aware task editing may not yet have the
    desktop-compatible dependency table, so upgrade it idempotently before the web
    facade starts issuing dependency-aware reads or transitions.
    """
    if project_management is None or getattr(project_management, "database_path", None) is not None:
        return
    connect = getattr(project_management, "_connect", None)
    if not callable(connect):
        return
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                ("fieldora_project_task_dependency_schema_v1",),
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pm_task_dependencies(
                    task_id TEXT NOT NULL REFERENCES pm_tasks(task_id) ON DELETE CASCADE,
                    depends_on_task_id TEXT NOT NULL REFERENCES pm_tasks(task_id) ON DELETE CASCADE,
                    dependency_type TEXT NOT NULL DEFAULT 'finish_to_start',
                    PRIMARY KEY(task_id,depends_on_task_id),
                    CHECK(task_id<>depends_on_task_id)
                )
                """
            )
