from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from natureai_next.server.api import ApiResponse
from natureai_next.server.research_records_api import ResearchRecordsApiMixin


@dataclass
class _Identity:
    identity_id: str = "researcher-1"
    organization_id: str = "org-1"


class _Science:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, tuple[dict, int]]] = {}

    def records(self, collection: str):
        return tuple(dict(item) for item, _revision in self.items.get(collection, {}).values())

    def put(self, collection: str, record: dict, expected_revision: int | None):
        bucket = self.items.setdefault(collection, {})
        record_id = str(record["id"])
        current = bucket.get(record_id)
        revision = 0 if current is None else current[1]
        if expected_revision is not None and expected_revision != revision:
            raise ValueError("revision_conflict")
        next_revision = revision + 1
        bucket[record_id] = (dict(record), next_revision)
        return next_revision


class _Decision:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed


class _Decisions:
    def __init__(self) -> None:
        self.allowed = True
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return _Decision(self.allowed)


class _Base:
    def __init__(self) -> None:
        self._science = _Science()
        self._decisions = _Decisions()
        self.identity = _Identity()
        self.generic_calls: list[tuple[str, str]] = []

    def _identity(self, _headers):
        return "token", self.identity

    def dispatch(self, method, target, _headers, _body):
        self.generic_calls.append((method, target))
        return ApiResponse.json(404, {"error": "not_found"})


class _Api(ResearchRecordsApiMixin, _Base):
    pass


def _payload(response: ApiResponse) -> dict:
    return json.loads(response.body)


def _create(api: _Api, domain: str = "specimens", **changes) -> dict:
    payload = {
        "project_id": "project-1",
        "name": "Voucher 1",
        "status": "active",
        "parent_id": "",
        "description": "Wetland voucher",
        "payload": {"catalogue": "A-1"},
    }
    payload.update(changes)
    response = api.dispatch(
        "POST", f"/api/v1/{domain}", {}, json.dumps(payload).encode()
    )
    assert response.status == 201
    return _payload(response)["item"]


@pytest.mark.parametrize(
    ("domain", "resource_type"),
    (
        ("specimens", "specimen"),
        ("encounters", "encounter"),
        ("protocols", "protocol"),
        ("survey-events", "survey_event"),
        ("enrichments", "enrichment"),
        ("samples", "sample"),
        ("laboratory-records", "laboratory_record"),
    ),
)
def test_create_is_server_owned_revisioned_and_pbac_scoped(
    domain: str, resource_type: str
) -> None:
    api = _Api()
    item = _create(api, domain, name=f"{domain} record")

    assert item["id"]
    assert item["organization_id"] == "org-1"
    assert item["project_id"] == "project-1"
    assert item["record_type"] == domain
    assert item["revision"] == 1
    assert item["created_by_identity_id"] == "researcher-1"
    assert api._decisions.requests[-1].action == "edit"
    assert api._decisions.requests[-1].resource_type == resource_type

    paths = [target for _method, target in api.generic_calls]
    assert f"/api/v1/{domain}" not in paths


def test_caller_cannot_forge_identity_revision_or_server_audit_fields() -> None:
    api = _Api()
    response = api.dispatch(
        "POST",
        "/api/v1/specimens",
        {},
        json.dumps(
            {
                "id": "caller-id",
                "project_id": "project-1",
                "name": "Forged",
                "revision": 8,
                "recorded_by": "someone-else",
            }
        ).encode(),
    )
    assert response.status == 400
    assert _payload(response)["error"] == "invalid_research_record"
    assert api._science.records("pm_specimens") == ()


def test_list_and_item_reads_are_project_filtered_pbac_and_tenant_safe() -> None:
    api = _Api()
    first = _create(api, name="First")
    second = _create(api, name="Second", project_id="project-2")

    listed = api.dispatch("GET", "/api/v1/specimens?project_id=project-1", {}, b"")
    assert listed.status == 200
    assert [item["id"] for item in _payload(listed)["items"]] == [first["id"]]

    read = api.dispatch("GET", f"/api/v1/specimens/{first['id']}", {}, b"")
    assert read.status == 200
    assert _payload(read)["item"]["name"] == "First"

    api._decisions.allowed = False
    hidden = api.dispatch("GET", f"/api/v1/specimens/{second['id']}", {}, b"")
    assert hidden.status == 404

    api._decisions.allowed = True
    api.identity = _Identity(identity_id="researcher-2", organization_id="org-2")
    cross_tenant = api.dispatch("GET", f"/api/v1/specimens/{first['id']}", {}, b"")
    assert cross_tenant.status == 404


def test_edit_requires_revision_and_preserves_project_identity_and_audit_ownership() -> None:
    api = _Api()
    item = _create(api)
    record_id = item["id"]

    missing = api.dispatch(
        "PATCH", f"/api/v1/specimens/{record_id}", {}, b'{"name":"Changed"}'
    )
    assert missing.status == 428
    assert _payload(missing)["error"] == "revision_required"

    stale = api.dispatch(
        "PATCH",
        f"/api/v1/specimens/{record_id}",
        {"if-match": "9"},
        b'{"name":"Changed"}',
    )
    assert stale.status == 409
    assert _payload(stale)["error"] == "revision_conflict"

    immutable_project = api.dispatch(
        "PATCH",
        f"/api/v1/specimens/{record_id}",
        {"if-match": "1"},
        b'{"project_id":"project-2"}',
    )
    assert immutable_project.status == 400

    updated = api.dispatch(
        "PATCH",
        f"/api/v1/specimens/{record_id}",
        {"if-match": "1"},
        b'{"name":"Voucher revised","description":"Reviewed"}',
    )
    assert updated.status == 200
    result = _payload(updated)
    assert result["revision"] == 2
    assert result["item"]["revision"] == 2
    assert result["item"]["project_id"] == "project-1"
    assert result["item"]["created_by_identity_id"] == "researcher-1"
    assert result["item"]["updated_by_identity_id"] == "researcher-1"


def test_unsupported_mutations_never_fall_through_to_generic_science_routes() -> None:
    api = _Api()
    item = _create(api)
    for method, target in (
        ("PUT", "/api/v1/specimens"),
        ("DELETE", "/api/v1/specimens"),
        ("PUT", f"/api/v1/specimens/{item['id']}"),
        ("DELETE", f"/api/v1/specimens/{item['id']}"),
    ):
        response = api.dispatch(method, target, {}, b"{}")
        assert response.status == 405
    governed_targets = {target for _method, target in api.generic_calls}
    assert not any(target.startswith("/api/v1/specimens") for target in governed_targets)
