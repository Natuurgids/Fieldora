from __future__ import annotations

import json
from contextlib import AbstractContextManager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from natureai_next.server.api import ApiResponse
from natureai_next.server.project_idempotency import (
    IdempotentProjectManagementFacade,
    ProjectIdempotencyApiMixin,
    ProjectMutationConflict,
)
from natureai_next.server.project_idempotency_web import (
    _PROJECT_IDEMPOTENCY_PATCH,
    ProjectIdempotencyWebApiMixin,
)


class _Cursor(AbstractContextManager["_Cursor"]):
    def __init__(self, project_row=None) -> None:
        self.project_row = project_row
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, parameters=()) -> None:
        self.statements.append((" ".join(sql.split()), tuple(parameters)))

    def fetchone(self):
        return self.project_row


class _Connection(AbstractContextManager["_Connection"]):
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self) -> _Cursor:
        return self._cursor


class _ProjectDelegate:
    def __init__(self, project_row=None) -> None:
        self.cursor = _Cursor(project_row)
        self.events: list[tuple[str, str, str, dict[str, object]]] = []

    def _connect(self) -> _Connection:
        return _Connection(self.cursor)

    def _event(
        self,
        cursor: _Cursor,
        project_id: str,
        actor_id: str,
        event_type: str,
        details: dict[str, object],
    ) -> None:
        self.events.append((project_id, actor_id, event_type, details))


def _project_row(
    *,
    organization_id: str = "org-1",
    name: str = "Wetland Survey",
    description: str = "Seasonal field survey",
    owner_id: str = "user-1",
) -> tuple[object, ...]:
    return (
        organization_id,
        name,
        description,
        "active",
        owner_id,
        "2026-09-01",
        "2026-12-31",
        1250.5,
        "EUR",
        None,
    )


def _create_with(facade: IdempotentProjectManagementFacade, project_id: str):
    return facade.create_project_idempotent(
        project_id,
        "Wetland Survey",
        organization_id="org-1",
        owner_id="user-1",
        actor_id="user-1",
        start_date="2026-09-01",
        due_date="2026-12-31",
        description="Seasonal field survey",
        budget=1250.5,
        currency="EUR",
    )


def test_project_create_uses_caller_identity_under_transaction_lock() -> None:
    project_id = str(uuid4())
    delegate = _ProjectDelegate()
    facade = IdempotentProjectManagementFacade(delegate)  # type: ignore[arg-type]

    created_id, replayed = _create_with(facade, project_id)

    assert created_id == project_id
    assert replayed is False
    statements = delegate.cursor.statements
    assert any("pg_advisory_xact_lock" in sql for sql, _ in statements)
    project_inserts = [
        parameters
        for sql, parameters in statements
        if sql.startswith("INSERT INTO pm_projects")
    ]
    assert len(project_inserts) == 1
    assert project_inserts[0][0] == project_id
    assert sum(sql.startswith("INSERT INTO pm_statuses") for sql, _ in statements) == 5
    assert sum(
        sql.startswith("INSERT INTO pm_project_members") for sql, _ in statements
    ) == 1
    assert delegate.events == [
        (project_id, "user-1", "project.created", {"name": "Wetland Survey"})
    ]


def test_exact_project_replay_returns_existing_without_side_effects() -> None:
    project_id = str(uuid4())
    delegate = _ProjectDelegate(_project_row())
    facade = IdempotentProjectManagementFacade(delegate)  # type: ignore[arg-type]

    existing_id, replayed = _create_with(facade, project_id)

    assert existing_id == project_id
    assert replayed is True
    assert not any(
        sql.startswith("INSERT INTO") for sql, _ in delegate.cursor.statements
    )
    assert delegate.events == []


def test_changed_payload_reusing_project_mutation_identity_conflicts() -> None:
    project_id = str(uuid4())
    delegate = _ProjectDelegate(_project_row(name="Another Project"))
    facade = IdempotentProjectManagementFacade(delegate)  # type: ignore[arg-type]

    with pytest.raises(ProjectMutationConflict, match="another payload"):
        _create_with(facade, project_id)

    assert not any(
        sql.startswith("INSERT INTO") for sql, _ in delegate.cursor.statements
    )
    assert delegate.events == []


class _DecisionService:
    def decide(self, request):
        return SimpleNamespace(allowed=True)


class _IdempotentService:
    def __init__(self) -> None:
        self.requests: dict[str, tuple[object, ...]] = {}

    def create_project_idempotent(self, project_id: str, name: str, **kwargs):
        request = (
            name,
            kwargs["organization_id"],
            kwargs["owner_id"],
            kwargs["start_date"],
            kwargs["due_date"],
            kwargs["description"],
            float(kwargs["budget"]),
            kwargs["currency"],
            kwargs["template_id"],
        )
        previous = self.requests.get(project_id)
        if previous is not None and previous != request:
            raise ProjectMutationConflict("project mutation identity already belongs to another payload")
        replayed = previous is not None
        self.requests[project_id] = request
        return project_id, replayed


class _ProjectApi(ProjectIdempotencyApiMixin):
    def __init__(self) -> None:
        self._project_management = _IdempotentService()
        self._decisions = _DecisionService()
        self.owner_grants: list[str] = []
        self.project = SimpleNamespace(revision=7)

    def _identity(self, headers):
        return "token", SimpleNamespace(identity_id="user-1", organization_id="org-1")

    def _grant_project_owner(
        self, identity_id: str, organization_id: str, project_id: str, name: str
    ) -> None:
        self.owner_grants.append(project_id)

    def _project_for_organization(self, organization_id: str, project_id: str):
        return self.project

    @staticmethod
    def _project_item(item):
        return {"revision": item.revision}


def _response_payload(response: ApiResponse) -> dict[str, object]:
    return json.loads(response.body.decode("utf-8"))


def test_api_exact_replay_is_successful_and_owner_grant_is_not_repeated() -> None:
    api = _ProjectApi()
    project_id = str(uuid4())
    body = json.dumps({"id": project_id, "name": "Wetland Survey"}).encode()

    first = api.dispatch("POST", "/api/v1/projects", {}, body)
    replay = api.dispatch("POST", "/api/v1/projects", {}, body)

    assert first.status == 201
    assert _response_payload(first)["replayed"] is False
    assert replay.status == 200
    assert _response_payload(replay)["replayed"] is True
    assert api.owner_grants == [project_id]


def test_api_changed_payload_reusing_mutation_identity_returns_conflict() -> None:
    api = _ProjectApi()
    project_id = str(uuid4())
    first = json.dumps({"id": project_id, "name": "Wetland Survey"}).encode()
    changed = json.dumps({"id": project_id, "name": "Changed"}).encode()

    assert api.dispatch("POST", "/api/v1/projects", {}, first).status == 201
    conflict = api.dispatch("POST", "/api/v1/projects", {}, changed)

    assert conflict.status == 409
    assert _response_payload(conflict) == {"error": "idempotency_conflict"}
    assert api.owner_grants == [project_id]


class _AppBase:
    def dispatch(self, method, target, headers, body):
        return ApiResponse(200, b"const appBase=true;", "application/javascript")


class _AppApi(ProjectIdempotencyWebApiMixin, _AppBase):
    pass


def test_browser_patch_reuses_one_project_identity_until_success() -> None:
    response = _AppApi().dispatch("GET", "/app.js", {}, b"")
    script = response.body.decode("utf-8")
    patch = _PROJECT_IDEMPOTENCY_PATCH.decode("utf-8")

    assert script.endswith(patch)
    assert 'if(kind==="project")beginProjectMutation()' in patch
    assert 'path==="/api/v1/projects"&&method==="POST"' in patch
    assert "record.id=projectMutationId" in patch
    assert "const result=await previousApi(path,options);\n    clearProjectMutation();" in patch
    assert "Keep the mutation identity after transport/server failure" in patch
