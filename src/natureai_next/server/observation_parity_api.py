"""Managed observation mutations aligned with the desktop evidence-first contract.

Desktop observations are owned by an existing evidence asset.  This mixin keeps that
invariant at the managed HTTP boundary: creation links an existing governed media
record, never uploads/copies evidence, generates the observation identifier server
side, and stores the same core observation fields used by the desktop schema.
"""

from __future__ import annotations

import json
import time
from uuid import uuid4
from urllib.parse import urlsplit

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


class ObservationParityApiMixin:
    """Own observation create/edit semantics before the legacy generic science route."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        path = urlsplit(target).path
        if path == "/api/v1/observations" and method == "POST":
            return self._create_observation(headers, body)
        prefix = "/api/v1/observations/"
        if path.startswith(prefix) and method in {"PATCH", "PUT"}:
            observation_id = path.removeprefix(prefix).strip("/")
            if observation_id:
                return self._edit_observation(observation_id, headers, body)
        return super().dispatch(method, target, headers, body)

    def _create_observation(
        self, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        auth = self._observation_identity(headers)
        if isinstance(auth, ApiResponse):
            return auth
        identity = auth
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            data = self._json_object(body)
            project_id = self._required_text(data, "project_id")
            asset_id = self._required_text(data, "asset_id")
            observation_type = self._observation_type(data.get("observation_type", "unknown"))
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
        }
        try:
            revision = self._science.put("server_observations", record, 0)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(201, {"item": record, "revision": revision})

    def _edit_observation(
        self,
        observation_id: str,
        headers: dict[str, str],
        body: bytes,
    ) -> ApiResponse:
        auth = self._observation_identity(headers)
        if isinstance(auth, ApiResponse):
            return auth
        identity = auth
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        expected = headers.get("if-match")
        if expected is None:
            return ApiResponse.json(428, {"error": "revision_required"})
        try:
            expected_revision = int(expected)
            if expected_revision < 1:
                raise ValueError
            changes = self._json_object(body)
        except (TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_observation"})
        if any(key not in _MUTABLE_FIELDS for key in changes):
            return ApiResponse.json(400, {"error": "immutable_observation_field"})

        current = next(
            (
                item
                for item in self._science.records("server_observations")
                if str(item.get("id", "")) == observation_id
            ),
            None,
        )
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
            confirmation = str(updated.get("confirmation_state", "unconfirmed")).strip()
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
        updated["updated_at_us"] = int(time.time() * 1_000_000)
        try:
            revision = self._science.put(
                "server_observations", updated, expected_revision
            )
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(200, {"item": updated, "revision": revision})

    def _observation_identity(self, headers: dict[str, str]):
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed as exc:
            return ApiResponse.json(
                401, {"error": "unauthorized", "detail": str(exc)}
            )
        if self._governance is not None:
            quota = self._governance.consume(identity.organization_id, "api_requests")
            if not quota.allowed:
                retry_after = max(1, quota.resets_at_epoch - int(time.time()))
                return ApiResponse(
                    429,
                    json.dumps(
                        {
                            "error": "tenant_quota_exceeded",
                            "metric": quota.metric,
                            "limit": quota.limit,
                            "used": quota.used,
                        },
                        separators=(",", ":"),
                    ).encode(),
                    "application/json; charset=utf-8",
                    headers=(("Retry-After", str(retry_after)),),
                )
        return identity

    def _observation_allowed(
        self, identity, headers: dict[str, str], action: str, resource_id: str, project_id: str
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
