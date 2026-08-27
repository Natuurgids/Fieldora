"""Governed Research-record parity for the managed browser.

The legacy generic Science routes accepted caller-owned public IDs and whole-record
replacement. WEB-042 gives the seven Research workspace domains a server-owned,
revisioned lifecycle while retaining their established Science collection names.
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
from natureai_next.server.research_records_web import patch_research_records_response

_DOMAINS = {
    "specimens": ("pm_specimens", "specimen"),
    "encounters": ("pm_encounters", "encounter"),
    "protocols": ("pm_protocols", "protocol"),
    "survey-events": ("pm_survey_events", "survey_event"),
    "enrichments": ("pm_enrichments", "enrichment"),
    "samples": ("pm_samples", "sample"),
    "laboratory-records": ("pm_laboratory_records", "laboratory_record"),
}
_PROTECTED_FIELDS = {
    "id",
    "revision",
    "organization_id",
    "record_type",
    "created_by_identity_id",
    "created_at_us",
    "updated_by_identity_id",
    "updated_at_us",
    "recorded_by",
    "recorded_at",
}
_MUTABLE_FIELDS = {"name", "status", "parent_id", "description", "payload"}
_GATE_PATH = "/api/v1/__research_record_governance_gate__"


class ResearchRecordsApiMixin:
    """Own Research-domain collection/item routes before the generic Science API."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        matched = self._research_route(route.path)
        if matched is None:
            response = super().dispatch(method, target, headers, body)
            return patch_research_records_response(target, response)

        domain, record_id = matched
        supported = (
            (not record_id and method in {"GET", "POST"})
            or (bool(record_id) and method in {"GET", "PATCH"})
        )
        if not supported:
            return ApiResponse.json(405, {"error": "method_not_allowed"})

        routed_headers = self._research_headers(headers)
        gate = super().dispatch("DELETE", _GATE_PATH, routed_headers, b"")
        if gate.status != 404:
            return gate
        try:
            _token, identity = self._identity(routed_headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})

        collection, resource_type = _DOMAINS[domain]
        if not record_id and method == "GET":
            response = self._list_research_records(
                collection,
                resource_type,
                route.query,
                identity,
                routed_headers,
            )
        elif not record_id:
            response = self._create_research_record(
                domain,
                collection,
                resource_type,
                identity,
                routed_headers,
                body,
            )
        elif method == "GET":
            response = self._get_research_record(
                collection,
                resource_type,
                record_id,
                identity,
                routed_headers,
            )
        else:
            response = self._update_research_record(
                collection,
                resource_type,
                record_id,
                identity,
                routed_headers,
                body,
            )
        return patch_research_records_response(target, response)

    @staticmethod
    def _research_route(path: str) -> tuple[str, str] | None:
        prefix = "/api/v1/"
        if not path.startswith(prefix):
            return None
        tail = path[len(prefix) :].strip("/")
        if not tail:
            return None
        parts = tail.split("/")
        domain = parts[0]
        if domain not in _DOMAINS or len(parts) > 2:
            return None
        record_id = "" if len(parts) == 1 else unquote(parts[1]).strip()
        if len(parts) == 2 and (not record_id or "/" in record_id):
            return None
        return domain, record_id

    def _list_research_records(
        self, collection, resource_type, query_string, identity, headers
    ) -> ApiResponse:
        project_filter = parse_qs(query_string).get("project_id", [""])[0].strip()
        items: list[dict] = []
        for raw in self._science.records(collection):
            item = dict(raw)
            if str(item.get("organization_id", identity.organization_id)) != identity.organization_id:
                continue
            project_id = str(item.get("project_id", ""))
            if project_filter and project_id != project_filter:
                continue
            if self._research_allowed(
                identity,
                headers,
                "view",
                resource_type,
                str(item.get("id", "")),
                project_id,
            ):
                items.append(item)
        return ApiResponse.json(200, {"items": items, "count": len(items)})

    def _get_research_record(
        self, collection, resource_type, record_id, identity, headers
    ) -> ApiResponse:
        item = self._current_research_record(collection, record_id)
        if item is None or str(item.get("organization_id", identity.organization_id)) != identity.organization_id:
            return ApiResponse.json(404, {"error": "not_found"})
        project_id = str(item.get("project_id", ""))
        if not self._research_allowed(
            identity, headers, "view", resource_type, record_id, project_id
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        return ApiResponse.json(200, {"item": item, "revision": int(item.get("revision", 1))})

    def _create_research_record(
        self, domain, collection, resource_type, identity, headers, body: bytes
    ) -> ApiResponse:
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            data = self._json_object(body)
            if _PROTECTED_FIELDS.intersection(data):
                raise ValueError("protected field")
            project_id = self._required_text(data, "project_id")
            name = self._required_text(data, "name")
            unknown = set(data) - ({"project_id"} | _MUTABLE_FIELDS)
            if unknown:
                raise ValueError("unsupported field")
            payload = data.get("payload", {})
            if not isinstance(payload, dict):
                raise ValueError("payload must be object")
        except (TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_research_record"})

        record_id = str(uuid4())
        if not self._research_allowed(
            identity, headers, "edit", resource_type, record_id, project_id
        ):
            return ApiResponse.json(403, {"error": "forbidden"})
        now_us = int(time.time() * 1_000_000)
        record = {
            "id": record_id,
            "organization_id": identity.organization_id,
            "project_id": project_id,
            "record_type": domain,
            "name": name,
            "status": str(data.get("status", "active")).strip() or "active",
            "parent_id": str(data.get("parent_id", "")).strip(),
            "description": str(data.get("description", "")).strip(),
            "payload": payload,
            "created_by_identity_id": identity.identity_id,
            "created_at_us": now_us,
            "updated_by_identity_id": identity.identity_id,
            "updated_at_us": now_us,
            "revision": 1,
        }
        try:
            revision = self._science.put(collection, record, 0)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(201, {"item": record, "revision": revision})

    def _update_research_record(
        self, collection, resource_type, record_id, identity, headers, body: bytes
    ) -> ApiResponse:
        expected = self._expected_revision(headers)
        if isinstance(expected, ApiResponse):
            return expected
        try:
            changes = self._json_object(body)
            if not changes or set(changes) - _MUTABLE_FIELDS:
                raise ValueError("mutable fields only")
            if "name" in changes and not str(changes["name"]).strip():
                raise ValueError("name required")
            if "payload" in changes and not isinstance(changes["payload"], dict):
                raise ValueError("payload must be object")
        except (TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_research_record"})

        current = self._current_research_record(collection, record_id)
        if current is None or str(current.get("organization_id", identity.organization_id)) != identity.organization_id:
            return ApiResponse.json(404, {"error": "not_found"})
        if int(current.get("revision", 1)) != expected:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        project_id = str(current.get("project_id", ""))
        if not self._research_allowed(
            identity, headers, "edit", resource_type, record_id, project_id
        ):
            return ApiResponse.json(403, {"error": "forbidden"})

        updated = dict(current)
        for field in _MUTABLE_FIELDS:
            if field not in changes:
                continue
            value = changes[field]
            updated[field] = value if field == "payload" else str(value or "").strip()
        updated["updated_by_identity_id"] = identity.identity_id
        updated["updated_at_us"] = int(time.time() * 1_000_000)
        updated["revision"] = expected + 1
        try:
            revision = self._science.put(collection, updated, expected)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(200, {"item": updated, "revision": revision})

    def _current_research_record(self, collection: str, record_id: str) -> dict | None:
        return next(
            (
                dict(item)
                for item in self._science.records(collection)
                if str(item.get("id", "")) == record_id
            ),
            None,
        )

    def _research_allowed(
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
        value = headers.get("if-match")
        if value is None:
            return ApiResponse.json(428, {"error": "revision_required"})
        try:
            revision = int(value)
            if revision < 1:
                raise ValueError
        except (TypeError, ValueError):
            return ApiResponse.json(400, {"error": "invalid_revision"})
        return revision

    @staticmethod
    def _json_object(body: bytes) -> dict:
        value = json.loads(body)
        if not isinstance(value, dict):
            raise TypeError("JSON object required")
        return value

    @staticmethod
    def _required_text(data: dict, field: str) -> str:
        value = str(data.get(field, "")).strip()
        if not value:
            raise ValueError(f"{field} required")
        return value

    @staticmethod
    def _research_headers(headers: dict[str, str]) -> dict[str, str]:
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
