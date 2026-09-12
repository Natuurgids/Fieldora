from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

from natureai_next.domain.science import ScienceRevision, ScienceRevisionConflict
from natureai_next.server.api import ApiResponse
from natureai_next.server.dossier_composition_web import patch_dossier_composition_response
from natureai_next.server.dossier_delete_api import DossierDeleteApiMixin


class _BaseApi:
    def dispatch(self, method, target, headers, body):
        if target == "/app.js" and method == "GET":
            return ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8")
        return ApiResponse.json(404, {"error": "not_found"})


class _Decisions:
    def __init__(self, denied=()) -> None:
        self.denied = set(denied)
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        allowed = (request.action, request.resource_id) not in self.denied
        return SimpleNamespace(allowed=allowed)


class _Science:
    def __init__(self, *, conflict: bool = False) -> None:
        self.snapshot = {
            "schema_version": 4,
            "dossiers": [
                {
                    "id": "master-1",
                    "organization_id": "org-1",
                    "project_id": "project-1",
                    "name": "Wetland master",
                    "description": "Master description",
                    "dossier_type": "master",
                    "review_status": "draft",
                },
                {
                    "id": "child-1",
                    "organization_id": "org-1",
                    "project_id": "project-2",
                    "name": "Bird survey",
                    "description": "Independent child",
                    "dossier_type": "dossier",
                    "review_status": "in_review",
                },
                {
                    "id": "candidate-1",
                    "organization_id": "org-1",
                    "project_id": "",
                    "name": "Water samples",
                    "description": "Independent candidate",
                    "dossier_type": "dossier",
                    "review_status": "draft",
                },
                {
                    "id": "ordinary-1",
                    "organization_id": "org-1",
                    "project_id": "project-1",
                    "name": "Ordinary dossier",
                    "dossier_type": "dossier",
                },
                {
                    "id": "foreign-1",
                    "organization_id": "org-2",
                    "project_id": "project-9",
                    "name": "Foreign dossier",
                    "dossier_type": "dossier",
                },
            ],
            "dossier_links": [
                {
                    "id": "link-1",
                    "parent_dossier_id": "master-1",
                    "child_dossier_id": "child-1",
                    "relationship": "contains",
                }
            ],
            "dossier_whiteboards": [
                {"dossier_id": "child-1", "board_id": "board-child"}
            ],
            "whiteboards": [{"id": "board-child", "title": "Child board"}],
        }
        self.revision = ScienceRevision(11)
        self.conflict = conflict
        self.saved = []

    def load_snapshot(self):
        return deepcopy(self.snapshot), self.revision

    def save_snapshot(self, snapshot, *, expected_revision):
        self.saved.append((deepcopy(snapshot), expected_revision))
        if self.conflict:
            raise ScienceRevisionConflict("changed")
        self.snapshot = deepcopy(snapshot)
        self.revision = ScienceRevision(expected_revision.database_revision + 1)
        return self.revision


class _Api(DossierDeleteApiMixin, _BaseApi):
    def __init__(self, *, denied=(), conflict: bool = False, organization_id="org-1"):
        self._science = _Science(conflict=conflict)
        self._decisions = _Decisions(denied)
        self.organization_id = organization_id

    def _identity(self, headers):
        return "token", SimpleNamespace(
            identity_id="owner-1",
            organization_id=self.organization_id,
        )


def _json(response):
    return json.loads(response.body)


def test_master_composition_projection_is_explicit_and_preserves_child_independence() -> None:
    api = _Api()

    response = api.dispatch(
        "GET",
        "/api/v1/dossiers/master-1/composition",
        {"x-fieldora-purpose": "research"},
        b"",
    )

    assert response.status == 200
    payload = _json(response)
    assert payload["revision"] == 11
    item = payload["item"]
    assert item["is_master"] is True
    assert item["master"]["id"] == "master-1"
    assert [child["id"] for child in item["children"]] == ["child-1"]
    assert item["children"][0]["project_id"] == "project-2"
    assert item["children"][0]["review_status"] == "in_review"
    assert item["children"][0]["relationship_id"] == "link-1"
    assert {child["id"] for child in item["available_children"]} == {
        "candidate-1",
        "ordinary-1",
    }
    assert api._science.saved == []


def test_master_composition_projection_filters_inaccessible_children_and_candidates() -> None:
    api = _Api(denied={("view", "child-1"), ("view", "candidate-1")})

    response = api.dispatch(
        "GET",
        "/api/v1/dossiers/master-1/composition",
        {},
        b"",
    )

    assert response.status == 200
    item = _json(response)["item"]
    assert item["children"] == []
    assert [candidate["id"] for candidate in item["available_children"]] == [
        "ordinary-1"
    ]


def test_add_child_creates_only_relationship_and_is_idempotent() -> None:
    api = _Api()

    created = api.dispatch(
        "POST",
        "/api/v1/dossiers/master-1/composition",
        {},
        b'{"child_dossier_id":"candidate-1"}',
    )

    assert created.status == 201
    assert _json(created)["revision"] == 12
    saved, expected_revision = api._science.saved[0]
    assert expected_revision == ScienceRevision(11)
    assert len(saved["dossiers"]) == 5
    candidate = next(item for item in saved["dossiers"] if item["id"] == "candidate-1")
    assert candidate["project_id"] == ""
    assert candidate["review_status"] == "draft"
    assert saved["dossier_whiteboards"] == [
        {"dossier_id": "child-1", "board_id": "board-child"}
    ]
    assert saved["whiteboards"] == [{"id": "board-child", "title": "Child board"}]
    assert {
        (link["parent_dossier_id"], link["child_dossier_id"], link["relationship"])
        for link in saved["dossier_links"]
    } == {
        ("master-1", "child-1", "contains"),
        ("master-1", "candidate-1", "contains"),
    }

    repeated = api.dispatch(
        "POST",
        "/api/v1/dossiers/master-1/composition",
        {},
        b'{"child_dossier_id":"candidate-1"}',
    )
    assert repeated.status == 200
    assert len(api._science.saved) == 1


def test_remove_child_deletes_only_relationship() -> None:
    api = _Api()

    response = api.dispatch(
        "DELETE",
        "/api/v1/dossiers/master-1/composition/child-1",
        {},
        b"",
    )

    assert response.status == 200
    saved, expected_revision = api._science.saved[0]
    assert expected_revision == ScienceRevision(11)
    assert saved["dossier_links"] == []
    assert any(item["id"] == "child-1" for item in saved["dossiers"])
    assert saved["dossier_whiteboards"] == [
        {"dossier_id": "child-1", "board_id": "board-child"}
    ]
    assert saved["whiteboards"] == [{"id": "board-child", "title": "Child board"}]


def test_master_composition_rejects_invalid_scope_and_non_master_mutation() -> None:
    foreign = _Api(organization_id="org-2")
    foreign_response = foreign.dispatch(
        "GET",
        "/api/v1/dossiers/master-1/composition",
        {},
        b"",
    )
    assert foreign_response.status == 404
    assert foreign._science.saved == []

    denied = _Api(denied={("edit", "master-1")})
    denied_response = denied.dispatch(
        "POST",
        "/api/v1/dossiers/master-1/composition",
        {},
        b'{"child_dossier_id":"candidate-1"}',
    )
    assert denied_response.status == 404
    assert denied._science.saved == []

    ordinary = _Api()
    ordinary_response = ordinary.dispatch(
        "POST",
        "/api/v1/dossiers/ordinary-1/composition",
        {},
        b'{"child_dossier_id":"candidate-1"}',
    )
    assert ordinary_response.status == 409
    assert _json(ordinary_response)["error"] == "dossier_not_master"
    assert ordinary._science.saved == []


def test_master_composition_reports_revision_conflict_without_partial_mutation() -> None:
    api = _Api(conflict=True)

    response = api.dispatch(
        "POST",
        "/api/v1/dossiers/master-1/composition",
        {},
        b'{"child_dossier_id":"candidate-1"}',
    )

    assert response.status == 409
    assert _json(response)["error"] == "revision_conflict"
    assert api._science.snapshot["dossier_links"] == [
        {
            "id": "link-1",
            "parent_dossier_id": "master-1",
            "child_dossier_id": "child-1",
            "relationship": "contains",
        }
    ]


def test_master_composition_web_patch_is_idempotent_and_uses_service_boundary() -> None:
    api = _Api()
    patched = api.dispatch("GET", "/app.js", {}, b"")
    again = patch_dossier_composition_response("/app.js", patched)

    assert patched.status == 200
    assert patched.body == again.body
    script = patched.body.decode()
    assert "WEB-DOSSIER-COMPOSITION" in script
    assert 'contractName="dossiers.composition.service"' in script
    assert "/composition" in script
    assert 'id="dossier-composition-panel"' in script
    assert 'id="dossier-composition-add"' in script
    assert 'data-dossier-composition-remove' in script
    assert 'fieldora:dossier-composition-changed' in script
    presentation = script.split("const state={mounted:false", 1)[1]
    assert "api(" not in presentation
