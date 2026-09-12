from __future__ import annotations

import json
from types import SimpleNamespace

from natureai_next.domain.access_control import IdentityKind
from natureai_next.server.api import ApiResponse
from natureai_next.server.dossier_lifecycle_api import DossierLifecycleApiMixin
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi


class _BaseApi:
    def dispatch(self, method, target, headers, body):
        return ApiResponse.json(404, {"error": "not_found"})


class _Decisions:
    def __init__(self, denied_actions=()):
        self.denied_actions = set(denied_actions)
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return SimpleNamespace(allowed=request.action not in self.denied_actions)


class _Science:
    def __init__(self):
        self.items = {
            "dossier-1": {
                "id": "dossier-1",
                "organization_id": "org-1",
                "project_id": "project-1",
                "name": "Wetland dossier",
                "description": "Initial description",
                "owner_id": "owner-1",
                "reviewer_id": "",
                "review_status": "draft",
                "review_history": [],
            }
        }
        self.revision = 3
        self.put_calls = []

    def records(self, collection):
        assert collection == "dossiers"
        return tuple(dict(item) for item in self.items.values())

    def put(self, collection, record, expected_revision):
        assert collection == "dossiers"
        self.put_calls.append((dict(record), expected_revision))
        if expected_revision is not None and expected_revision != self.revision:
            raise ValueError("revision_conflict")
        self.revision += 1
        self.items[str(record["id"])] = dict(record)
        return self.revision


class _Access:
    def __init__(self):
        self.items = {
            "owner-1": SimpleNamespace(
                identity_id="owner-1",
                organization_id="org-1",
                kind=IdentityKind.USER,
                enabled=True,
            ),
            "owner-2": SimpleNamespace(
                identity_id="owner-2",
                organization_id="org-1",
                kind=IdentityKind.USER,
                enabled=True,
            ),
            "disabled-owner": SimpleNamespace(
                identity_id="disabled-owner",
                organization_id="org-1",
                kind=IdentityKind.USER,
                enabled=False,
            ),
            "other-org-owner": SimpleNamespace(
                identity_id="other-org-owner",
                organization_id="org-2",
                kind=IdentityKind.USER,
                enabled=True,
            ),
            "service-owner": SimpleNamespace(
                identity_id="service-owner",
                organization_id="org-1",
                kind=IdentityKind.SERVICE,
                enabled=True,
            ),
        }

    def identity(self, identity_id):
        return self.items.get(identity_id)


class _Api(DossierLifecycleApiMixin, _BaseApi):
    def __init__(self, denied_actions=(), identity_id="owner-1"):
        self._science = _Science()
        self._decisions = _Decisions(denied_actions)
        self._access_repository = _Access()
        self.identity_id = identity_id

    def _identity(self, headers):
        return "token", SimpleNamespace(
            identity_id=self.identity_id,
            organization_id="org-1",
        )


def _json(response):
    return json.loads(response.body)


def test_dossier_edit_is_revisioned_and_preserves_governed_identity_fields() -> None:
    api = _Api()

    response = api.dispatch(
        "PATCH",
        "/api/v1/dossiers/dossier-1",
        {"if-match": "3", "x-fieldora-purpose": "research"},
        json.dumps(
            {
                "name": "Wetland dossier revised",
                "description": "Updated description",
                "dossier_type": "master",
                "owner_id": "attacker",
                "reviewer_id": "attacker",
                "organization_id": "other-org",
            }
        ).encode(),
    )

    assert response.status == 200
    payload = _json(response)
    assert payload["revision"] == 4
    item = payload["item"]
    assert item["id"] == "dossier-1"
    assert item["organization_id"] == "org-1"
    assert item["owner_id"] == "owner-1"
    assert item["reviewer_id"] == ""
    assert item["name"] == "Wetland dossier revised"
    assert item["description"] == "Updated description"
    assert item["dossier_type"] == "master"
    assert item["updated_by"] == "owner-1"
    assert api._science.put_calls[0][1] == 3


def test_dossier_edit_rejects_unsupported_dossier_type() -> None:
    api = _Api()

    response = api.dispatch(
        "PATCH",
        "/api/v1/dossiers/dossier-1",
        {},
        b'{"dossier_type":"project"}',
    )

    assert response.status == 400
    assert _json(response)["error"] == "invalid_dossier_type"
    assert api._science.put_calls == []


def test_dossier_edit_fails_closed_without_edit_authority() -> None:
    api = _Api({"edit"})

    response = api.dispatch(
        "PATCH",
        "/api/v1/dossiers/dossier-1",
        {},
        b'{"name":"Forbidden"}',
    )

    assert response.status == 404
    assert api._science.put_calls == []


def test_dossier_edit_reports_revision_conflict() -> None:
    api = _Api()

    response = api.dispatch(
        "PATCH",
        "/api/v1/dossiers/dossier-1",
        {"if-match": "2"},
        b'{"description":"Stale"}',
    )

    assert response.status == 409
    assert _json(response)["error"] == "revision_conflict"


def test_dossier_administrator_can_reassign_owner_with_provenance() -> None:
    api = _Api(identity_id="administrator-1")

    response = api.dispatch(
        "POST",
        "/api/v1/dossiers/dossier-1/owner/reassign",
        {"x-fieldora-purpose": "research"},
        b'{"owner_id":"owner-2"}',
    )

    assert response.status == 200
    item = _json(response)["item"]
    assert item["owner_id"] == "owner-2"
    assert item["updated_by"] == "administrator-1"
    assert item["review_history"][-1]["action"] == "owner_reassigned"
    assert item["review_history"][-1]["actor_id"] == "administrator-1"
    assert item["review_history"][-1]["remark"] == "owner-1 → owner-2"
    assert api._decisions.requests[-1].action == "reassign_owner"


def test_dossier_owner_reassignment_fails_closed_without_admin_authority() -> None:
    api = _Api({"reassign_owner"}, identity_id="owner-1")

    response = api.dispatch(
        "POST",
        "/api/v1/dossiers/dossier-1/owner/reassign",
        {},
        b'{"owner_id":"owner-2"}',
    )

    assert response.status == 404
    assert api._science.put_calls == []


def test_dossier_owner_reassignment_requires_owner_identity() -> None:
    api = _Api(identity_id="administrator-1")

    response = api.dispatch(
        "POST",
        "/api/v1/dossiers/dossier-1/owner/reassign",
        {},
        b'{"owner_id":""}',
    )

    assert response.status == 400
    assert _json(response)["error"] == "owner_required"
    assert api._science.put_calls == []


def test_dossier_owner_reassignment_rejects_ineligible_target_identities() -> None:
    for owner_id in (
        "missing-owner",
        "disabled-owner",
        "other-org-owner",
        "service-owner",
    ):
        api = _Api(identity_id="administrator-1")

        response = api.dispatch(
            "POST",
            "/api/v1/dossiers/dossier-1/owner/reassign",
            {},
            json.dumps({"owner_id": owner_id}).encode(),
        )

        assert response.status == 404
        assert _json(response)["error"] == "owner_not_found"
        assert api._science.put_calls == []


def test_dossier_owner_can_defer_to_named_reviewer_with_provenance() -> None:
    api = _Api()

    response = api.dispatch(
        "POST",
        "/api/v1/dossiers/dossier-1/review/defer",
        {},
        b'{"reviewer_id":"reviewer-1","remark":"Please check taxonomy"}',
    )

    assert response.status == 200
    item = _json(response)["item"]
    assert item["owner_id"] == "owner-1"
    assert item["reviewer_id"] == "reviewer-1"
    assert item["review_status"] == "in_review"
    assert item["review_history"][-1]["action"] == "deferred_for_review"
    assert item["review_history"][-1]["actor_id"] == "owner-1"
    assert item["review_history"][-1]["remark"] == "Please check taxonomy"


def test_assigned_reviewer_can_remark_and_return_dossier() -> None:
    api = _Api(identity_id="reviewer-1")
    api._science.items["dossier-1"]["reviewer_id"] = "reviewer-1"
    api._science.items["dossier-1"]["review_status"] = "in_review"

    remarked = api.dispatch(
        "POST",
        "/api/v1/dossiers/dossier-1/review/remark",
        {},
        b'{"remark":"Add location evidence"}',
    )
    returned = api.dispatch(
        "POST",
        "/api/v1/dossiers/dossier-1/review/return",
        {},
        b'{"remark":"Please revise"}',
    )

    assert remarked.status == 200
    assert returned.status == 200
    item = _json(returned)["item"]
    assert item["review_status"] == "returned"
    assert [entry["action"] for entry in item["review_history"]] == [
        "review_remark",
        "returned_to_observer",
    ]
    assert item["review_history"][0]["actor_id"] == "reviewer-1"
    assert item["review_history"][1]["remark"] == "Please revise"


def test_unassigned_identity_cannot_act_as_dossier_reviewer() -> None:
    api = _Api(identity_id="other-user")
    api._science.items["dossier-1"]["reviewer_id"] = "reviewer-1"
    api._science.items["dossier-1"]["review_status"] = "in_review"

    response = api.dispatch(
        "POST",
        "/api/v1/dossiers/dossier-1/review/return",
        {},
        b'{"remark":"No"}',
    )

    assert response.status == 404
    assert api._science.put_calls == []


def test_lifecycle_route_does_not_capture_dossier_evidence_routes() -> None:
    api = _Api()

    response = api.dispatch(
        "GET",
        "/api/v1/dossiers/dossier-1/media-links",
        {},
        b"",
    )

    assert response.status == 404


def test_dossier_lifecycle_api_is_composed_between_presentation_and_evidence() -> None:
    mro = OfflineFirstFieldoraApi.__mro__
    presentation = next(base for base in mro if base.__name__ == "DossierModuleWebApiMixin")
    lifecycle = next(base for base in mro if base.__name__ == "DossierLifecycleApiMixin")
    evidence = next(base for base in mro if base.__name__ == "DossierEvidenceApiMixin")

    assert mro.index(presentation) < mro.index(lifecycle) < mro.index(evidence)
