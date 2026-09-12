from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

import pytest

from natureai_next.application.project_management import ProjectManagementService
from natureai_next.server.browser_functionality_api import BrowserFunctionalityFieldoraApi
from natureai_next.server.postgres_project_management import (
    ManagedProjectSummary,
    PostgresProjectManagementService,
)


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


def _managed_service() -> tuple[PostgresProjectManagementService, _Cursor]:
    cursor = _Cursor()
    connection = _Connection(cursor)
    return PostgresProjectManagementService(lambda: connection), cursor


def _managed_project_insert(cursor: _Cursor) -> tuple[object, ...]:
    return next(
        params
        for sql, params in cursor.calls
        if "INSERT INTO pm_projects(" in sql
    )


def test_desktop_and_managed_project_create_normalize_same_project_fields(tmp_path) -> None:
    database = tmp_path / "desktop-projects.sqlite3"
    desktop = ProjectManagementService(database)
    managed, cursor = _managed_service()

    desktop.create_project(
        "  Field survey  ",
        owner_id="  owner-1  ",
        actor_id="actor-1",
        start_date="2026-08-01",
        due_date="2026-08-31",
        description="  Habitat survey  ",
        budget=1250,
        currency=" eur ",
    )
    managed.create_project(
        "  Field survey  ",
        organization_id=" org-1 ",
        owner_id="  owner-1  ",
        actor_id="actor-1",
        start_date="2026-08-01",
        due_date="2026-08-31",
        description="  Habitat survey  ",
        budget=1250,
        currency=" eur ",
    )

    with sqlite3.connect(database) as connection:
        desktop_row = connection.execute(
            "SELECT name,description,status,owner_id,start_date,due_date,budget,currency "
            "FROM pm_projects"
        ).fetchone()
    assert desktop_row is not None

    managed_insert = _managed_project_insert(cursor)
    managed_row = (
        managed_insert[2],
        managed_insert[3],
        "active",
        managed_insert[4],
        managed_insert[5],
        managed_insert[6],
        managed_insert[7],
        managed_insert[8],
    )
    assert managed_row == desktop_row
    assert managed_insert[1] == "org-1"


@pytest.mark.parametrize(
    ("name", "start_date", "due_date", "message"),
    [
        ("   ", "", "", "project name is required"),
        ("Project", "2026-99-01", "", "project start date must use YYYY-MM-DD"),
        (
            "Project",
            "2026-08-31",
            "2026-08-01",
            "project due date cannot be before its start date",
        ),
    ],
)
def test_desktop_and_managed_reject_same_invalid_project_fields(
    tmp_path, name: str, start_date: str, due_date: str, message: str
) -> None:
    desktop = ProjectManagementService(tmp_path / "desktop-projects.sqlite3")
    managed, _cursor = _managed_service()

    with pytest.raises(ValueError, match=message):
        desktop.create_project(
            name,
            owner_id="owner-1",
            actor_id="actor-1",
            start_date=start_date,
            due_date=due_date,
        )
    with pytest.raises(ValueError, match=message):
        managed.create_project(
            name,
            organization_id="org-1",
            owner_id="owner-1",
            actor_id="actor-1",
            start_date=start_date,
            due_date=due_date,
        )


def test_managed_project_requires_server_organization() -> None:
    managed, _cursor = _managed_service()
    with pytest.raises(ValueError, match="organization is required"):
        managed.create_project(
            "Project",
            organization_id="   ",
            owner_id="owner-1",
            actor_id="actor-1",
        )


class _Allow:
    def decide(self, _request):
        return SimpleNamespace(allowed=True)


class _ApiProjectService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.project: ManagedProjectSummary | None = None

    def create_project(self, name: str, **kwargs) -> str:
        self.calls.append({"name": name, **kwargs})
        project_id = "project-1"
        self.project = ManagedProjectSummary(
            project_id=project_id,
            organization_id=str(kwargs["organization_id"]),
            name=name.strip(),
            status="active",
            owner_id=str(kwargs["owner_id"]),
            start_date=str(kwargs["start_date"]),
            due_date=str(kwargs["due_date"]),
            budget=float(kwargs["budget"]),
            currency=str(kwargs["currency"]),
            description=str(kwargs["description"]).strip(),
            revision=7,
        )
        return project_id

    def projects(self, organization_id: str):
        if self.project is None or self.project.organization_id != organization_id:
            return ()
        return (self.project,)


class _Api(BrowserFunctionalityFieldoraApi):
    def __init__(self, service: _ApiProjectService) -> None:
        self._project_management = service
        self._decisions = _Allow()
        self._access_repository = None

    def _identity(self, _headers):
        return "token", SimpleNamespace(
            identity_id="creator-1", organization_id="org-authenticated"
        )


def test_web_project_transport_uses_authenticated_owner_and_organization() -> None:
    service = _ApiProjectService()
    api = _Api(service)

    response = api._create_project(
        {"x-fieldora-purpose": "research"},
        json.dumps(
            {
                "name": "  Web project  ",
                "owner_id": "attacker-selected-owner",
                "organization_id": "attacker-selected-org",
                "start_date": "2026-08-01",
                "due_date": "2026-08-31",
                "description": "  Browser description  ",
                "budget": 42,
                "currency": "EUR",
            }
        ).encode("utf-8"),
    )

    assert response.status == 201
    assert len(service.calls) == 1
    call = service.calls[0]
    assert call["name"] == "Web project"
    assert call["owner_id"] == "creator-1"
    assert call["actor_id"] == "creator-1"
    assert call["organization_id"] == "org-authenticated"
    assert call["description"] == "  Browser description  "
    assert call["start_date"] == "2026-08-01"
    assert call["due_date"] == "2026-08-31"
