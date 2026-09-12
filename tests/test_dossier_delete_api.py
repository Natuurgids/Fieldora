from __future__ import annotations

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
                    "title": "Target dossier",
                },
                {
                    "id": "dossier-2",
                    "organization_id": "org-1",
                    "project_id": "project-1",
                    "title": "Other dossier",
                },
            ],
            "dossier_whiteboards": [
                {"dossier_id": "dossier-1", "board_id": "board-shared"},
                {"dossier_id": "dossier-2", "board_id": "board-shared"},
            ],
            "dossier_links": [
                {
                    "id": "link-parent",
                    "parent_dossier_id": "dossier-1",
                    "child_dossier_id": "dossier-2",
                    "relationship": "contains",
                },
                {
                    "id": "link-child",
                    "parent_dossier_id": "dossier-2",
                    "child_dossier_id": "dossier-1",
                    "relationship": "contains",
                },
                {
                    "id": "link-unrelated",
                    "parent_dossier_id": "dossier-2",
                    "child_dossier_id": "dossier-3",
                    "relationship": "contains",
                },
            ],
            "whiteboards": [{"id": "board-shared", "title": "Shared board"}],
            "whiteboard_elements": [
                {"id": "element-1", "board_id": "board-shared", "kind": "note"}
            ],
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
        raise AssertionError(f"Dossier deletion must not mutate Library media: {name}")


class _Api(DossierDeleteApiMixin, _BaseApi):
    def __init__(self, *, allowed: bool = True, conflict: bool = False) -> None:
        self._science = _Science(conflict=conflict)
        self._decisions = _Decisions(allowed)
        self._media = _MediaSentinel()

    def _identity(self, headers):
        return "token", SimpleNamespace(
            identity_id="owner-1",
            organization_id=headers.get("x-test-organization", "org-1"),
        )


def test_delete_dossier_uses_one_snapshot_and_preserves_shared_documents() -> None:
    api = _Api()

    response = api.dispatch(
        "DELETE",
        "/api/v1/dossiers/dossier-1",
        {"x-fieldora-purpose": "research"},
        b"",
    )

    assert response.status == 204
    assert response.body == b""
    assert len(api._science.saved) == 1
    saved, expected_revision = api._science.saved[0]
    assert expected_revision == ScienceRevision(7)
    assert [item["id"] for item in saved["dossiers"]] == ["dossier-2"]
    assert saved["dossier_whiteboards"] == [
        {"dossier_id": "dossier-2", "board_id": "board-shared"}
    ]
    assert saved["dossier_links"] == [
        {
            "id": "link-unrelated",
            "parent_dossier_id": "dossier-2",
            "child_dossier_id": "dossier-3",
            "relationship": "contains",
        }
    ]
    assert saved["whiteboards"] == [
        {"id": "board-shared", "title": "Shared board"}
    ]
    assert saved["whiteboard_elements"] == [
        {"id": "element-1", "board_id": "board-shared", "kind": "note"}
    ]
    request = api._decisions.requests[0]
    assert request.action == "edit"
    assert request.resource_type == "dossier"
    assert request.resource_id == "dossier-1"


def test_delete_dossier_fails_closed_for_other_organization() -> None:
    api = _Api()

    response = api.dispatch(
        "DELETE",
        "/api/v1/dossiers/dossier-1",
        {"x-test-organization": "org-2"},
        b"",
    )

    assert response.status == 404
    assert api._science.saved == []
    assert api._decisions.requests == []


def test_delete_dossier_fails_closed_without_edit_authority() -> None:
    api = _Api(allowed=False)

    response = api.dispatch("DELETE", "/api/v1/dossiers/dossier-1", {}, b"")

    assert response.status == 404
    assert api._science.saved == []


def test_delete_dossier_reports_snapshot_revision_conflict() -> None:
    api = _Api(conflict=True)

    response = api.dispatch("DELETE", "/api/v1/dossiers/dossier-1", {}, b"")

    assert response.status == 409
    assert len(api._science.saved) == 1
