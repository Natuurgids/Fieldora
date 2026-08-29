from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from natureai_next.application.project_management import ProjectManagementService


ROOT = Path(__file__).resolve().parents[1]


def test_qt_project_creation_delegates_to_shared_project_service() -> None:
    source = (ROOT / "src/natureai_next/ui/qt/project_management.py").read_text(
        encoding="utf-8"
    )

    assert "self._project_id = self._service.create_project(" in source
    assert "owner_id=owner.strip()" in source
    assert "actor_id=self._actor_provider()" in source
    assert "due_date=due.strip()" in source
    assert "self.refresh()" in source


def test_desktop_project_create_contract_persists_defaults_owner_audit_and_selection_id(
    tmp_path,
) -> None:
    database = tmp_path / "desktop-projects.sqlite3"
    service = ProjectManagementService(database)

    project_id = service.create_project(
        "  Meadow survey  ",
        owner_id="owner-1",
        actor_id="actor-1",
        due_date="2026-10-31",
    )

    with sqlite3.connect(database) as connection:
        project = connection.execute(
            "SELECT project_id,name,status,owner_id,start_date,due_date,budget,currency,"
            "created_at_us,updated_at_us FROM pm_projects WHERE project_id=?",
            (project_id,),
        ).fetchone()
        member = connection.execute(
            "SELECT user_id,role FROM pm_project_members WHERE project_id=?",
            (project_id,),
        ).fetchone()
        activity = connection.execute(
            "SELECT actor_id,event_type,details_json FROM pm_activity "
            "WHERE project_id=? ORDER BY event_id",
            (project_id,),
        ).fetchone()

    assert project is not None
    assert project[:8] == (
        project_id,
        "Meadow survey",
        "active",
        "owner-1",
        "",
        "2026-10-31",
        0.0,
        "EUR",
    )
    assert project[8] == project[9]
    assert member == ("owner-1", "admin")
    assert activity is not None
    assert activity[0] == "actor-1"
    assert activity[1] == "project.created"
    assert json.loads(activity[2]) == {"name": "  Meadow survey  "}
