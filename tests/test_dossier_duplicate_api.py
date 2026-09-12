from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

from natureai_next.domain.science import ScienceRevision, ScienceRevisionConflict
from natureai_next.server.api import ApiResponse
from natureai_next.server.dossier_delete_api import DossierDeleteApiMixin


class _BaseApi:
    def dispatch(self, method, target, headers, body):
        return ApiResponse.json(404, {"error": "not_found"})


class _Decisions:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return SimpleNamespace(allowed=self.allowed)


class _Science:
    def __init__(self, *, conflict: bool = False) -> None:
        self.snapshot = {
            "schema_version": 4,
            "dossiers": [
                {
                    "id": "dossier-1",
                    "organization_id": "org-1",
                    "project_id": "project-1",
                    "name": "Wetland dossier",
                    "description": "Source description",
                    "owner_id": "owner-1",
                    "reviewer_id": "reviewer-1",
                    "review_status": "in_review",
                    "review_history": [
                        {
                            "action": "deferred_for_review",
                            "actor_id": "owner-1",
                            "remark": "Check taxonomy",
                        }
                    ],
                },
                {
                    "id": "dossier-2",
                    "organization_id": "org-1",
                    "project_id": "project-1",
                    "name": "Other dossier",
                },
            ],
            "dossier_whiteboards": [
                {"dossier_id": "dossier-1", "board_id": "board-shared"},
                {"dossier_id": "dossier-2", "board_id": "board-shared"},
            ],
            "dossier_links": [
                {
                    "id": "link-1",
                    "parent_dossier_id": "dossier-1",
                    "child_dossier_id": "dossier-2",
                    "relationship": "contains",
                }
            ],
            "whiteboards": [{"id": "board-shared", "title": "Shared board"}],
        }
        self.revision = ScienceRevision(7)
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


class _MediaSentinel:
    def __getattr__(self, name):
        raise AssertionError(f"Dossier duplication must not mutate Library media: {name}")


class _Api(DossierDeleteApiMixin, _BaseApi):
    def __init__(self, *, allowed: bool = True, conflict: bool = False) -> None:
        self._science = _Science(conflict=conflict)
        self._decisions = _Decisions(allowed)
        self._media = _MediaSentinel()

    def _identity(self, headers):
        return "token", SimpleNamespace(
            identity_id="owner-2",
            organization_id=headers.get("x-test-organization", "org-1"),
        )


def _json(response):
    return json.loads(response.body)


def test_duplicate_dossier_creates_fresh_draft_and_preserves_shared_science_links() -> None:
    api = _Api()

    response = api.dispatch(
        "POST",
        "/api/v1/dossiers/dossier-1/duplicate",
        {"x-fieldora-purpose": "research"},
        b"",
    )

    assert response.status == 201
    payload = _json(response)
    assert payload["revision"] == 8
    item = payload["item"]
    assert item["id"] != "dossier-1"
    assert item["source_dossier_id"] == "dossier-1"
    assert item["name"] == "Wetland dossier (copy)"
    assert item["description"] == "Source description"
    assert item["owner_id"] == "owner-2"
    assert item["created_by"] == "owner-2"
    assert item["updated_by"] == "owner-2"
    assert item["reviewer_id"] == ""
    assert item["review_status"] == "draft"
    assert [entry["action"] for entry in item["review_history"]] == [
        "dossier_duplicated"
    ]
    assert item["review_history"][0]["actor_id"] == "owner-2"
    assert item["review_history"][0]["remark"] == "Duplicated from dossier-1"

    saved, expected_revision = api._science.saved[0]
    assert expected_revision == ScienceRevision(7)
    assert [record["id"] for record in saved["dossiers"][:2]] == [
        "dossier-1",
        "dossier-2",
    ]
    assert saved["dossiers"][0]["review_status"] == "in_review"
    assert saved["dossier_whiteboards"][-1] == {
        "dossier_id": item["id"],
        "board_id": "board-shared",
    }
    assert saved["whiteboards"] == [{"id": "board-shared", "title": "Shared board"}]
    assert saved["dossier_links"] == [
        {
            "id": "link-1",
            "parent_dossier_id": "dossier-1",
            "child_dossier_id": "dossier-2",
            "relationship": "contains",
        }
    ]
    request = api._decisions.requests[0]
    assert request.action == "edit"
    assert request.resource_type == "dossier"
    assert request.resource_id == "dossier-1"


def test_duplicate_dossier_allows_explicit_copy_name_without_governed_field_override() -> None:
    api = _Api()

    response = api.dispatch(
        "POST",
        "/api/v1/dossiers/dossier-1/duplicate",
        {},
        b'{"name":"Survey follow-up","owner_id":"attacker","review_status":"approved"}',
    )

    assert response.status == 201
    item = _json(response)["item"]
    assert item["name"] == "Survey follow-up"
    assert item["owner_id"] == "owner-2"
    assert item["review_status"] == "draft"


def test_duplicate_dossier_rejects_invalid_copy_name() -> None:
    api = _Api()

    response = api.dispatch(
        "POST",
        "/api/v1/dossiers/dossier-1/duplicate",
        {},
        b'{"name":"   "}',
    )

    assert response.status == 400
    assert _json(response)["error"] == "invalid_request"
    assert api._science.saved == []


def test_duplicate_dossier_fails_closed_for_other_organization() -> None:
    api = _Api()

    response = api.dispatch(
        "POST",
        "/api/v1/dossiers/dossier-1/duplicate",
        {"x-test-organization": "org-2"},
        b"",
    )

    assert response.status == 404
    assert api._science.saved == []
    assert api._decisions.requests == []


def test_duplicate_dossier_fails_closed_without_edit_authority() -> None:
    api = _Api(allowed=False)

    response = api.dispatch(
        "POST", "/api/v1/dossiers/dossier-1/duplicate", {}, b""
    )

    assert response.status == 404
    assert api._science.saved == []


def test_duplicate_dossier_reports_snapshot_revision_conflict() -> None:
    api = _Api(conflict=True)

    response = api.dispatch(
        "POST", "/api/v1/dossiers/dossier-1/duplicate", {}, b""
    )

    assert response.status == 409
    assert _json(response)["error"] == "revision_conflict"
    assert len(api._science.saved) == 1
