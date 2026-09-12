"""Managed-web parity for non-destructive Library collections and datasets.

Collections organize governed evidence by public ID. They never own, rewrite, or delete
the referenced evidence: membership is stored only on the collection record and every
mutation is revisioned and policy-authorized.
"""

from __future__ import annotations

import json
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.library_collections_web import patch_library_collections_web_response

_COLLECTIONS = "server_library_collections"
_GATE_PATH = "/api/v1/__library_collections_governance_gate__"
_PROTECTED_CREATE_FIELDS = {
    "id",
    "organization_id",
    "asset_public_ids",
    "revision",
    "created_at_us",
    "updated_at_us",
    "deleted_at_us",
}


class LibraryCollectionsApiMixin:
    """Own managed Library collection CRUD and membership before generic science routes."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        split = urlsplit(target)
        path = split.path
        root = path == "/api/v1/library/collections"
        prefix = "/api/v1/library/collections/"
        tail = path.removeprefix(prefix).strip("/") if path.startswith(prefix) else ""
        parts = tuple(part for part in tail.split("/") if part)
        item = len(parts) == 1
        membership = len(parts) == 2 and parts[1] == "assets"
        governed = root or item or membership
        supported = (
            (root and method in {"GET", "POST"})
            or (item and method in {"GET", "PATCH", "DELETE"})
            or (membership and method in {"POST", "DELETE"})
        )
        if not governed:
            response = super().dispatch(method, target, headers, body)
            return patch_library_collections_web_response(target, response)
        if not supported:
            return ApiResponse.json(405, {"error": "method_not_allowed"})

        routed_headers = self._library_collection_headers(headers)
        # Exercise the established managed lifecycle/session gates without probing a
        # real collection path, because generic routes may own similarly named records.
        gate = super().dispatch("DELETE", _GATE_PATH, routed_headers, b"")
        if gate.status != 404:
            return gate
        try:
            _token, identity = self._identity(routed_headers)
        except AuthenticationFailed as exc:
            return ApiResponse.json(401, {"error": "unauthorized", "detail": str(exc)})

        if root and method == "GET":
            project_id = parse_qs(split.query).get("project_id", [""])[0].strip()
            return self._list_library_collections(identity, routed_headers, project_id)
        if root and method == "POST":
            return self._create_library_collection(identity, routed_headers, body)

        collection_id = unquote(parts[0]) if parts else ""
        current = self._current_library_collection(collection_id, identity.organization_id)
        if current is None:
            return ApiResponse.json(404, {"error": "not_found"})
        project_id = str(current.get("project_id", ""))
        if item and method == "GET":
            if not self._library_collection_allowed(
                identity, routed_headers, "view", "collection", collection_id, project_id
            ):
                return ApiResponse.json(404, {"error": "not_found"})
            return ApiResponse.json(200, {"item": current, "revision": current["revision"]})
        if item and method == "PATCH":
            return self._update_library_collection(
                current, identity, routed_headers, body
            )
        if item and method == "DELETE":
            return self._delete_library_collection(current, identity, routed_headers)
        return self._mutate_library_collection_membership(
            current, identity, routed_headers, body, add=method == "POST"
        )

    def _list_library_collections(self, identity, headers, project_id: str) -> ApiResponse:
        items: list[dict] = []
        for raw in self._science.records(_COLLECTIONS):
            item = dict(raw)
            if item.get("deleted_at_us") is not None:
                continue
            if str(item.get("organization_id", "")) != identity.organization_id:
                continue
            item_project_id = str(item.get("project_id", ""))
            if project_id and item_project_id != project_id:
                continue
            if self._library_collection_allowed(
                identity,
                headers,
                "view",
                "collection",
                str(item.get("id", "")),
                item_project_id,
            ):
                items.append(item)
        items.sort(key=lambda value: (str(value.get("name", "")).casefold(), str(value.get("id", ""))))
        return ApiResponse.json(200, {"items": items})

    def _create_library_collection(self, identity, headers, body: bytes) -> ApiResponse:
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            data = self._json_object(body)
            if _PROTECTED_CREATE_FIELDS.intersection(data):
                raise ValueError("protected field")
            project_id = self._required_text(data, "project_id")
            name = self._required_text(data, "name")
            description = self._optional_text(data.get("description"))
        except (json.JSONDecodeError, TypeError, ValueError):
            return ApiResponse.json(400, {"error": "invalid_collection"})
        if not self._library_collection_allowed(
            identity, headers, "edit", "collection", "new", project_id
        ):
            return ApiResponse.json(403, {"error": "forbidden"})
        now_us = time.time_ns() // 1_000
        record = {
            "id": str(uuid4()),
            "organization_id": identity.organization_id,
            "project_id": project_id,
            "name": name,
            "description": description,
            "kind": "manual",
            "asset_public_ids": [],
            "revision": 1,
            "created_at_us": now_us,
            "updated_at_us": now_us,
            "deleted_at_us": None,
        }
        try:
            self._science.put(_COLLECTIONS, record, 0)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(201, {"item": record, "revision": 1})

    def _update_library_collection(self, current, identity, headers, body: bytes) -> ApiResponse:
        project_id = str(current.get("project_id", ""))
        collection_id = str(current.get("id", ""))
        if not self._library_collection_allowed(
            identity, headers, "edit", "collection", collection_id, project_id
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        expected = self._expected_revision(headers)
        if isinstance(expected, ApiResponse):
            return expected
        try:
            data = self._json_object(body)
            if not data or set(data) - {"name", "description"}:
                raise ValueError("unsupported field")
            updated = dict(current)
            if "name" in data:
                updated["name"] = self._required_text(data, "name")
            if "description" in data:
                updated["description"] = self._optional_text(data.get("description"))
        except (json.JSONDecodeError, TypeError, ValueError):
            return ApiResponse.json(400, {"error": "invalid_collection_update"})
        if expected != int(current.get("revision", 1)):
            return ApiResponse.json(409, {"error": "revision_conflict"})
        updated["revision"] = expected + 1
        updated["updated_at_us"] = time.time_ns() // 1_000
        try:
            self._science.put(_COLLECTIONS, updated, expected)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(200, {"item": updated, "revision": updated["revision"]})

    def _delete_library_collection(self, current, identity, headers) -> ApiResponse:
        project_id = str(current.get("project_id", ""))
        collection_id = str(current.get("id", ""))
        if not self._library_collection_allowed(
            identity, headers, "edit", "collection", collection_id, project_id
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        expected = self._expected_revision(headers)
        if isinstance(expected, ApiResponse):
            return expected
        if expected != int(current.get("revision", 1)):
            return ApiResponse.json(409, {"error": "revision_conflict"})
        updated = dict(current)
        now_us = time.time_ns() // 1_000
        updated["revision"] = expected + 1
        updated["updated_at_us"] = now_us
        updated["deleted_at_us"] = now_us
        try:
            self._science.put(_COLLECTIONS, updated, expected)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(
            200,
            {
                "deleted": True,
                "id": collection_id,
                "evidence_deleted": False,
                "revision": updated["revision"],
            },
        )

    def _mutate_library_collection_membership(
        self, current, identity, headers, body: bytes, *, add: bool
    ) -> ApiResponse:
        project_id = str(current.get("project_id", ""))
        collection_id = str(current.get("id", ""))
        action = "link" if add else "unlink"
        if not self._library_collection_allowed(
            identity, headers, action, "collection", collection_id, project_id
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        expected = self._expected_revision(headers)
        if isinstance(expected, ApiResponse):
            return expected
        try:
            data = self._json_object(body)
            raw_ids = data.get("asset_public_ids")
            if not isinstance(raw_ids, list):
                raise ValueError("asset_public_ids is required")
            asset_ids = tuple(dict.fromkeys(str(value).strip() for value in raw_ids if str(value).strip()))
            if not asset_ids or len(asset_ids) > 500:
                raise ValueError("asset count out of bounds")
        except (json.JSONDecodeError, TypeError, ValueError):
            return ApiResponse.json(400, {"error": "invalid_collection_membership"})
        for asset_id in asset_ids:
            if not self._library_collection_allowed(
                identity, headers, action, "asset", asset_id, project_id
            ):
                return ApiResponse.json(403, {"error": "forbidden"})
        if expected != int(current.get("revision", 1)):
            return ApiResponse.json(409, {"error": "revision_conflict"})

        existing = tuple(str(value) for value in current.get("asset_public_ids", []))
        if add:
            next_ids = tuple(dict.fromkeys((*existing, *asset_ids)))
        else:
            removed = set(asset_ids)
            next_ids = tuple(value for value in existing if value not in removed)
        updated = dict(current)
        updated["asset_public_ids"] = list(next_ids)
        updated["revision"] = expected + 1
        updated["updated_at_us"] = time.time_ns() // 1_000
        try:
            self._science.put(_COLLECTIONS, updated, expected)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(
            200,
            {
                "item": updated,
                "revision": updated["revision"],
                "membership_only": True,
                "evidence_mutated": False,
            },
        )

    def _current_library_collection(self, collection_id: str, organization_id: str) -> dict | None:
        return next(
            (
                dict(item)
                for item in self._science.records(_COLLECTIONS)
                if str(item.get("id", "")) == collection_id
                and str(item.get("organization_id", "")) == organization_id
                and item.get("deleted_at_us") is None
            ),
            None,
        )

    def _library_collection_allowed(
        self, identity, headers, action, resource_type, resource_id, project_id
    ) -> bool:
        return self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                resource_type,
                resource_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        ).allowed

    @staticmethod
    def _expected_revision(headers: dict[str, str]) -> int | ApiResponse:
        expected = headers.get("if-match")
        if expected is None:
            return ApiResponse.json(428, {"error": "revision_required"})
        try:
            revision = int(expected)
            if revision < 1:
                raise ValueError
        except (TypeError, ValueError):
            return ApiResponse.json(400, {"error": "invalid_revision"})
        return revision

    @staticmethod
    def _library_collection_headers(headers: dict[str, str]) -> dict[str, str]:
        routed = dict(headers)
        if routed.get("authorization"):
            return routed
        cookie = SimpleCookie()
        try:
            cookie.load(routed.get("cookie", ""))
        except Exception:
            return routed
        morsel = cookie.get("fieldora_session")
        if morsel is not None and morsel.value:
            routed["authorization"] = f"Bearer {morsel.value}"
        return routed

    @staticmethod
    def _json_object(body: bytes) -> dict:
        value = json.loads(body)
        if not isinstance(value, dict):
            raise TypeError("JSON object required")
        return value

    @staticmethod
    def _required_text(data: dict, field: str) -> str:
        value = " ".join(str(data.get(field, "")).split())
        if not value:
            raise ValueError(f"{field} is required")
        return value

    @staticmethod
    def _optional_text(value) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(str(value).split())
        return cleaned or None
