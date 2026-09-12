from __future__ import annotations

import json
from dataclasses import dataclass

from natureai_next.server.api import ApiResponse
from natureai_next.server.library_collections_api import LibraryCollectionsApiMixin


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
        current_revision = 0 if current is None else current[1]
        if expected_revision is not None and expected_revision != current_revision:
            raise ValueError("revision_conflict")
        revision = current_revision + 1
        bucket[record_id] = (dict(record), revision)
        return revision


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
        # This stands in for governed evidence storage and must never be mutated by
        # collection membership or collection deletion.
        self.evidence = {
            "asset-1": {"id": "asset-1", "source_snapshot": {"checksum": "sha256:a"}},
            "asset-2": {"id": "asset-2", "source_snapshot": {"checksum": "sha256:b"}},
        }

    def _identity(self, _headers):
        return "token", self.identity

    def dispatch(self, method, target, _headers, _body):
        self.generic_calls.append((method, target))
        return ApiResponse.json(404, {"error": "not_found"})


class _Api(LibraryCollectionsApiMixin, _Base):
    pass


def _payload(response: ApiResponse) -> dict:
    return json.loads(response.body)


def _create(api: _Api, **overrides) -> dict:
    payload = {"project_id": "project-1", "name": "Wetland evidence", "description": "August"}
    payload.update(overrides)
    response = api.dispatch(
        "POST", "/api/v1/library/collections", {}, json.dumps(payload).encode()
    )
    assert response.status == 201
    return _payload(response)["item"]


def test_create_is_server_owned_revisioned_and_does_not_accept_membership_forgery() -> None:
    api = _Api()
    response = api.dispatch(
        "POST",
        "/api/v1/library/collections",
        {},
        json.dumps(
            {
                "project_id": "project-1",
                "name": "Forged",
                "id": "caller-id",
                "organization_id": "other-org",
                "asset_public_ids": ["asset-1"],
            }
        ).encode(),
    )
    assert response.status == 400
    assert _payload(response)["error"] == "invalid_collection"

    item = _create(api)
    assert item["id"]
    assert item["organization_id"] == "org-1"
    assert item["project_id"] == "project-1"
    assert item["asset_public_ids"] == []
    assert item["revision"] == 1
    assert item["deleted_at_us"] is None
    assert all(path != "/api/v1/library/collections" for _method, path in api.generic_calls)


def test_link_unlink_edit_and_delete_only_mutate_collection_state() -> None:
    api = _Api()
    evidence_before = json.loads(json.dumps(api.evidence))
    item = _create(api)
    collection_id = item["id"]

    linked = api.dispatch(
        "POST",
        f"/api/v1/library/collections/{collection_id}/assets",
        {"if-match": "1"},
        b'{"asset_public_ids":["asset-1","asset-2","asset-1"]}',
    )
    assert linked.status == 200
    linked_payload = _payload(linked)
    assert linked_payload["item"]["asset_public_ids"] == ["asset-1", "asset-2"]
    assert linked_payload["revision"] == 2
    assert linked_payload["membership_only"] is True
    assert linked_payload["evidence_mutated"] is False
    assert api.evidence == evidence_before

    unlinked = api.dispatch(
        "DELETE",
        f"/api/v1/library/collections/{collection_id}/assets",
        {"if-match": "2"},
        b'{"asset_public_ids":["asset-1"]}',
    )
    assert unlinked.status == 200
    assert _payload(unlinked)["item"]["asset_public_ids"] == ["asset-2"]
    assert api.evidence == evidence_before

    edited = api.dispatch(
        "PATCH",
        f"/api/v1/library/collections/{collection_id}",
        {"if-match": "3"},
        b'{"name":"Wetland dataset","description":"Reviewed"}',
    )
    assert edited.status == 200
    assert _payload(edited)["item"]["name"] == "Wetland dataset"
    assert _payload(edited)["revision"] == 4

    deleted = api.dispatch(
        "DELETE",
        f"/api/v1/library/collections/{collection_id}",
        {"if-match": "4"},
        b"",
    )
    assert deleted.status == 200
    deleted_payload = _payload(deleted)
    assert deleted_payload["deleted"] is True
    assert deleted_payload["evidence_deleted"] is False
    assert api.evidence == evidence_before

    listed = api.dispatch("GET", "/api/v1/library/collections", {}, b"")
    assert listed.status == 200
    assert _payload(listed)["items"] == []


def test_revision_conflicts_and_missing_revision_are_explicit() -> None:
    api = _Api()
    item = _create(api)
    collection_id = item["id"]

    missing = api.dispatch(
        "PATCH",
        f"/api/v1/library/collections/{collection_id}",
        {},
        b'{"name":"Changed"}',
    )
    assert missing.status == 428
    assert _payload(missing)["error"] == "revision_required"

    stale = api.dispatch(
        "POST",
        f"/api/v1/library/collections/{collection_id}/assets",
        {"if-match": "9"},
        b'{"asset_public_ids":["asset-1"]}',
    )
    assert stale.status == 409
    assert _payload(stale)["error"] == "revision_conflict"


def test_policy_uses_edit_link_unlink_and_asset_scope() -> None:
    api = _Api()
    item = _create(api)
    collection_id = item["id"]
    api._decisions.requests.clear()

    response = api.dispatch(
        "POST",
        f"/api/v1/library/collections/{collection_id}/assets",
        {"if-match": "1", "x-fieldora-purpose": "research"},
        b'{"asset_public_ids":["asset-1"]}',
    )
    assert response.status == 200
    assert [(request.action, request.resource_type, request.resource_id) for request in api._decisions.requests] == [
        ("link", "collection", collection_id),
        ("link", "asset", "asset-1"),
    ]

    api._decisions.requests.clear()
    response = api.dispatch(
        "DELETE",
        f"/api/v1/library/collections/{collection_id}/assets",
        {"if-match": "2"},
        b'{"asset_public_ids":["asset-1"]}',
    )
    assert response.status == 200
    assert [(request.action, request.resource_type) for request in api._decisions.requests] == [
        ("unlink", "collection"),
        ("unlink", "asset"),
    ]


def test_policy_denial_and_tenant_isolation_do_not_expose_collection() -> None:
    api = _Api()
    item = _create(api)
    collection_id = item["id"]

    api._decisions.allowed = False
    denied = api.dispatch(
        "GET", f"/api/v1/library/collections/{collection_id}", {}, b""
    )
    assert denied.status == 404

    api._decisions.allowed = True
    api.identity = _Identity(identity_id="researcher-2", organization_id="org-2")
    cross_tenant = api.dispatch(
        "GET", f"/api/v1/library/collections/{collection_id}", {}, b""
    )
    assert cross_tenant.status == 404


def test_governed_namespace_never_falls_through_to_generic_collection_routes() -> None:
    api = _Api()
    unsupported = api.dispatch(
        "PUT", "/api/v1/library/collections/not-a-real-id", {}, b"{}"
    )
    assert unsupported.status == 405
    assert all(
        "/api/v1/library/collections" not in path
        for _method, path in api.generic_calls
    )
