"""Lossless Project task detail read model for desktop-parity web editing.

The normal task summary intentionally serves planning views and omits several
editable fields. This query object exposes the authoritative task row for a
single already-authorized Project context without coupling the web layer to the
SQLite schema directly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


class ProjectTaskDetailQuery:
    """Read one complete Project task record from the Project database."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)

    def get(self, project_id: str, task_id: str) -> dict[str, object] | None:
        project = project_id.strip()
        task = task_id.strip()
        if not project or not task:
            return None
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                """
                SELECT
                    t.task_id AS id,
                    t.task_id,
                    t.project_id,
                    t.parent_task_id,
                    t.title,
                    t.description,
                    t.status_id,
                    s.name AS status_name,
                    s.category AS status_category,
                    t.owner_id,
                    t.priority,
                    t.start_date,
                    t.due_date,
                    t.estimate_hours,
                    t.budget,
                    t.progress,
                    t.recurrence,
                    t.recurrence_end,
                    t.milestone,
                    t.sprint,
                    t.position,
                    t.phase_id,
                    t.sprint_id,
                    t.realized_hours
                FROM pm_tasks t
                JOIN pm_statuses s ON s.status_id=t.status_id
                WHERE t.project_id=? AND t.task_id=?
                """,
                (project, task),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        item = dict(row)
        item["milestone"] = bool(item.get("milestone"))
        return item
