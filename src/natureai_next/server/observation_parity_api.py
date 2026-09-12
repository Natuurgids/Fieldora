"""Managed observation mutations aligned with the desktop evidence-first contract.

Desktop observations retain one existing governed asset as primary evidence. Managed
web observations preserve that compatible pointer while allowing additional governed
evidence links. Linking never uploads, copies, or re-registers evidence; relationship
changes are explicit and revision-safe.
"""

from __future__ import annotations

import json
import time
from http.cookies import SimpleCookie
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse

_OBSERVATION_TYPES = {"organism", "habitat", "landscape", "unknown"}
_CONFIRMATION_STATES = {"unconfirmed", "confirmed", "rejected"}
_MUTABLE_FIELDS = {
    "taxon_id",
    "user_taxon_id",
    "observation_type",
    "life_stage",
    "sex",
    "count",
    "behavior",
    "notes",
    "confirmation_state",
    "region_of_interest_id",
}
_COLLECTION = "server_observations"


class ObservationParityApiMixin:
    """Own observation and evidence-link mutations before the generic science route."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        path = urlsplit(target).path
        create = path == "/api/v1/observations" and method == "POST"
        prefix = "/api/v1/observations/"
        tail = path.removeprefix(prefix).strip("/") if path.startswith(prefix) else ""
        parts = tuple(part for part in tail.split("/") if part)
        evidence_link = len(parts) == 2 and parts[1] == "evidence" and method == "POST"
        evidence_unlink = (
            len(parts) == 3 and parts[1] == "evidence" and method == "DELETE"
        )
        edit = len(parts) == 1 and method in {"PATCH", "PUT"}
        if not create and not edit and not evidence_link and not evidence_unlink:
            return super().dispatch(method, target, headers, body)

        routed_headers = self._observation_headers(headers)
        # Run a deliberately unsupported mutation through the established managed API.
        # This performs the existing service-lifecycle, authentication, tenant-quota,
        # and browser-session gates without invoking a legacy observation mutation.
        gate = super().dispatch("DELETE", path, routed_headers, b"")
        if gate.status != 404:
            return gate
        try:
            _token, identity = self._identity(routed_headers)
        except AuthenticationFailed as exc:
            return ApiResponse.json(
                401, {"error": "unauthorized", "detail": str(exc)}
            )

        if create:
            return self._create_observation(identity, routed_headers, body)
        observation_id = unquote(parts[0]) if parts else ""
        if not observation_id:
            return ApiResponse.json(404, {"error": "not_found"})
        if evidence_link:
            return self._link_observation_evidence(
                observation_id, identity, routed_headers, body
            )
        if evidence_unlink:
            return self._unlink_observation_evidence(
                observation_id,
                unquote(parts[2]),
                identity,
                routed_headers,
            )
        return self._edit_observation(
            observation_id, identity, routed_headers, body
        )

    def _create_observation(
        self, identity, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            data = self._json_object(body)
            project_id = self._required_text(data, "project_id")
            asset_id = self._required_text(data, "asset_id")
            observation_type = self._observation_type(
                data.get("observation_type", "unknown")
            )
            count = self._count(data.get("count"))
            taxon_id = self._optional_identifier(data.get("taxon_id"))
            user_taxon_id = self._optional_identifier(data.get("user_taxon_id"))
            if taxon_id is not None and user_taxon_id is not None:
                raise ValueError("taxon identifiers are mutually exclusive")
        except (TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_observation"})

        media_error = self._validate_observation_asset(
            asset_id, identity.organization_id, project_id
        )
        if media_error is not None:
            return media_error

        observation_id = str(uuid4())
        if not self._observation_allowed(
            identity, headers, "edit", observation_id, project_id
        ):
            return ApiResponse.json(403, {"error": "forbidden"})

        now_us = int(time.time() * 1_000_000)
        record = {
            "id": observation_id,
            "project_id": project_id,
            "asset_id": asset_id,
            "supporting_asset_ids": [],
            "taxon_id": taxon_id,
            "user_taxon_id": user_taxon_id,
            "observation_type": observation_type,
            "life_stage": self._optional_text(data.get("life_stage")),
            "sex": self._optional_text(data.get("sex")),
            "count": count,
            "behavior": self._optional_text(data.get("behavior")),
            "notes": self._optional_text(data.get("notes")),
            "confirmation_state": "unconfirmed",
            "source": "user",
            "region_of_interest_id": self._optional_identifier(
                data.get("region_of_interest_id")
            ),
            "created_at_us": now_us,
            "updated_at_us": now_us,
            "revision": 1,
        }
        try:
            revision = self._science.put(_COLLECTION, record, 0)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(201, {"item": record, "revision": revision})

    def _edit_observation(
        self,
        observation_id: str,
        identity,
        headers: dict[str, str],
        body: bytes,
    ) -> ApiResponse:
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        expected_revision = self._expected_revision(headers)
        if isinstance(expected_revision, ApiResponse):
            return expected_revision
        try:
            changes = self._json_object(body)
        except (TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_observation"})
        if any(key not in _MUTABLE_FIELDS for key in changes):
            return ApiResponse.json(400, {"error": "immutable_observation_field"})

        current = self._current_observation(observation_id)
        if current is None:
            return ApiResponse.json(404, {"error": "not_found"})
        project_id = str(current.get("project_id", ""))
        if not self._observation_allowed(
            identity, headers, "edit", observation_id, project_id
        ):
            return ApiResponse.json(403, {"error": "forbidden"})

        updated = dict(current)
        updated.update(changes)
        try:
            updated["observation_type"] = self._observation_type(
                updated.get("observation_type", "unknown")
            )
            updated["count"] = self._count(updated.get("count"))
            updated["taxon_id"] = self._optional_identifier(updated.get("taxon_id"))
            updated["user_taxon_id"] = self._optional_identifier(
                updated.get("user_taxon_id")
            )
            if updated["taxon_id"] is not None and updated["user_taxon_id"] is not None:
                raise ValueError("taxon identifiers are mutually exclusive")
            confirmation = str(
                updated.get("confirmation_state", "unconfirmed")
            ).strip()
            if confirmation not in _CONFIRMATION_STATES:
                raise ValueError("invalid confirmation state")
            updated["confirmation_state"] = confirmation
            for field in ("life_stage", "sex", "behavior", "notes"):
                updated[field] = self._optional_text(updated.get(field))
            updated["region_of_interest_id"] = self._optional_identifier(
                updated.get("region_of_interest_id")
            )
        except (TypeError, ValueError):
            return ApiResponse.json(400, {"error": "invalid_observation"})
        return self._put_observation(updated, expected_revision)

    def _link_observation_evidence(
        self,
        observation_id: str,
        identity,
        headers: dict[str, str],
        body: bytes,
    ) -> ApiResponse:
        expected_revision = self._expected_revision(headers)
        if isinstance(expected_revision, ApiResponse):
            return expected_revision
        try:
            data = self._json_object(body)
            asset_id = self._required_text(data, "asset_id")
        except (TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_evidence_link"})
        current = self._current_observation(observation_id)
        if current is None:
            return ApiResponse.json(404, {"error": "not_found"})
        authorization = self._authorize_evidence_change(
            current, identity, headers, observation_id, expected_revision
        )
        if authorization is not None:
            return authorization
        if asset_id == str(current.get("asset_id", "")):
            return ApiResponse.json(409, {"error": "evidence_already_primary"})
        media_error = self._validate_observation_asset(
            asset_id, identity.organization_id, str(current.get("project_id", ""))
        )
        if media_error is not None:
            return media_error
        supporting = self._supporting_asset_ids(current)
        if asset_id in supporting:
            return ApiResponse.json(
                200, {"item": current, "revision": expected_revision}
            )
        updated = dict(current)
        updated["supporting_asset_ids"] = [*supporting, asset_id]
        return self._put_observation(updated, expected_revision)

    def _unlink_observation_evidence(
        self,
        observation_id: str,
        asset_id: str,
        identity,
        headers: dict[str, str],
    ) -> ApiResponse:
        expected_revision = self._expected_revision(headers)
        if isinstance(expected_revision, ApiResponse):
            return expected_revision
        if not asset_id:
            return ApiResponse.json(400, {"error": "invalid_evidence_link"})
        current = self._current_observation(observation_id)
        if current is None:
            return ApiResponse.json(404, {"error": "not_found"})
        authorization = self._authorize_evidence_change(
            current, identity, headers, observation_id, expected_revision
        )
        if authorization is not None:
            return authorization
        if asset_id == str(current.get("asset_id", "")):
            return ApiResponse.json(409, {"error": "cannot_unlink_primary_evidence"})
        supporting = self._supporting_asset_ids(current)
        if asset_id not in supporting:
            return ApiResponse.json(
                200, {"item": current, "revision": expected_revision}
            )
        updated = dict(current)
        updated["supporting_asset_ids"] = [
            linked_id for linked_id in supporting if linked_id != asset_id
        ]
        return self._put_observation(updated, expected_revision)

    def _authorize_evidence_change(
        self,
        current: dict,
        identity,
        headers: dict[str, str],
        observation_id: str,
        expected_revision: int,
    ) -> ApiResponse | None:
        if int(current.get("revision", 0)) != expected_revision:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        project_id = str(current.get("project_id", ""))
        if not self._observation_allowed(
            identity, headers, "edit", observation_id, project_id
        ):
            return ApiResponse.json(403, {"error": "forbidden"})
        return None

    def _put_observation(self, updated: dict, expected_revision: int) -> ApiResponse:
        updated["supporting_asset_ids"] = list(self._supporting_asset_ids(updated))
        updated["updated_at_us"] = int(time.time() * 1_000_000)
        updated["revision"] = expected_revision + 1
        try:
            revision = self._science.put(_COLLECTION, updated, expected_revision)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(200, {"item": updated, "revision": revision})

    def _current_observation(self, observation_id: str) -> dict | None:
        current = next(
            (
                item
                for item in self._science.records(_COLLECTION)
                if str(item.get("id", "")) == observation_id
            ),
            None,
        )
        if current is None:
            return None
        normalized = dict(current)
        normalized["supporting_asset_ids"] = list(self._supporting_asset_ids(current))
        return normalized

    def _observation_allowed(
        self,
        identity,
        headers: dict[str, str],
        action: str,
        resource_id: str,
        project_id: str,
    ) -> bool:
        return self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                "observation",
                resource_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        ).allowed

    def _validate_observation_asset(
        self, asset_id: str, organization_id: str, project_id: str
    ) -> ApiResponse | None:
        if self._media is None:
            return ApiResponse.json(503, {"error": "evidence_store_unavailable"})
        record = self._media.record(asset_id)
        if record is None or record.organization_id != organization_id:
            return ApiResponse.json(404, {"error": "evidence_not_found"})
        if record.project_id and record.project_id != project_id:
            return ApiResponse.json(409, {"error": "evidence_project_mismatch"})
        return None

    @staticmethod
    def _supporting_asset_ids(record: dict) -> tuple[str, ...]:
        value = record.get("supporting_asset_ids", [])
        if not isinstance(value, (list, tuple)):
            return ()
        result: list[str] = []
        for item in value:
            asset_id = str(item).strip()
            if asset_id and asset_id not in result:
                result.append(asset_id)
        return tuple(result)

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
            return ApiResponse.json(400, {"error": "invalid_observation"})
        return revision

    @staticmethod
    def _observation_headers(headers: dict[str, str]) -> dict[str, str]:
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
        value = str(data.get(field, "")).strip()
        if not value:
            raise ValueError(f"{field} is required")
        return value

    @staticmethod
    def _optional_text(value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_identifier(value):
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            raise ValueError("boolean identifier")
        return value

    @staticmethod
    def _observation_type(value) -> str:
        text = str(value).strip().casefold()
        if text not in _OBSERVATION_TYPES:
            raise ValueError("invalid observation type")
        return text

    @staticmethod
    def _count(value) -> int | None:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            raise ValueError("invalid count")
        result = int(value)
        if result < 0 or str(result) != str(value).strip():
            raise ValueError("invalid count")
        return result
