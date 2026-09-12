"""Authenticated browser/server API for facility drawings, future layouts, and moves."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from natureai_next.domain.access_control import Identity
from natureai_next.server.api import ApiResponse
from natureai_next.server.facility_platform import PostgresFacilityPlatformRepository
from natureai_next.server.platform_api import PlatformFieldoraApi


class CompletePlatformFieldoraApi(PlatformFieldoraApi):
    """Complete managed-server edge including Facilities Planning."""

    PREFIX = "/api/v1/facility-planning"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        connect = getattr(self._science, "_connect", None)
        self._facility_platform = (
            PostgresFacilityPlatformRepository(connect) if callable(connect) else None
        )

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        path = urlsplit(target).path
        if not path.startswith(self.PREFIX):
            return super().dispatch(method, target, headers, body)
        gate = super().dispatch(method, target, headers, body)
        if gate.status != 404:
            return gate
        if self._facility_platform is None:
            return ApiResponse.json(
                501, {"error": "shared_facility_planning_requires_postgresql_science"}
            )
        _token, identity = self._identity(headers)
        return self._facility_dispatch(method, path, headers, body, identity)

    def _facility_dispatch(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
        identity: Identity,
    ) -> ApiResponse:
        suffix = path.removeprefix(self.PREFIX).strip("/")
        parts = [] if not suffix else suffix.split("/")
        repository = self._facility_platform
        assert repository is not None
        if parts == ["drawings"] and method == "GET":
            if not self._facility_allowed(identity, headers, "view", "drawing", ""):
                return ApiResponse.json(403, {"error": "forbidden"})
            items = repository.drawings()
            return ApiResponse.json(200, {"items": items, "count": len(items)})
        if len(parts) == 2 and parts[0] == "drawings" and method == "GET":
            if not self._facility_allowed(identity, headers, "view", "drawing", parts[1]):
                return ApiResponse.json(404, {"error": "not_found"})
            item = repository.drawing(parts[1])
            return (
                ApiResponse.json(200, {"drawing": item})
                if item is not None
                else ApiResponse.json(404, {"error": "not_found"})
            )
        if (
            len(parts) == 3
            and parts[0] == "drawings"
            and parts[2] == "geometries"
            and method == "POST"
        ):
            if not self._facility_allowed(identity, headers, "edit", "drawing", parts[1]):
                return ApiResponse.json(403, {"error": "forbidden"})
            try:
                data = self._json_object(body)
                item = repository.add_geometry(
                    parts[1],
                    location_id=str(data.get("location_id", "")),
                    geometry_type=str(data["geometry_type"]),
                    geometry=dict(data["geometry"]),
                    label=str(data.get("label", "")),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_geometry"})
            return ApiResponse.json(201, {"geometry": item})
        if parts == ["plans"] and method == "GET":
            if not self._facility_allowed(identity, headers, "view", "layout", ""):
                return ApiResponse.json(403, {"error": "forbidden"})
            items = repository.plans()
            return ApiResponse.json(200, {"items": items, "count": len(items)})
        if parts == ["plans"] and method == "POST":
            if not self._facility_allowed(identity, headers, "create", "layout", ""):
                return ApiResponse.json(403, {"error": "forbidden"})
            try:
                data = self._json_object(body)
                item = repository.create_plan(
                    name=str(data["name"]),
                    actor=identity.identity_id,
                    drawing_id=str(data.get("drawing_id", "")),
                    version=str(data.get("version", "")),
                    effective_at=str(data.get("effective_at", "")),
                    notes=str(data.get("notes", "")),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_layout_plan"})
            return ApiResponse.json(201, {"plan": item})
        if len(parts) == 2 and parts[0] == "plans" and method == "GET":
            if not self._facility_allowed(identity, headers, "view", "layout", parts[1]):
                return ApiResponse.json(404, {"error": "not_found"})
            item = repository.plan(parts[1])
            return (
                ApiResponse.json(200, {"plan": item})
                if item is not None
                else ApiResponse.json(404, {"error": "not_found"})
            )
        if (
            len(parts) == 3
            and parts[0] == "plans"
            and parts[2] == "placements"
            and method == "POST"
        ):
            if not self._facility_allowed(identity, headers, "update", "layout", parts[1]):
                return ApiResponse.json(403, {"error": "forbidden"})
            try:
                data = self._json_object(body)
                item = repository.plan_asset(
                    parts[1],
                    asset_id=str(data["asset_id"]),
                    target_location_id=str(data["target_location_id"]),
                    target_geometry_id=str(data.get("target_geometry_id", "")),
                    sequence=int(data.get("sequence", 0)),
                    notes=str(data.get("notes", "")),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_planned_placement"})
            return ApiResponse.json(201, {"placement": item})
        if parts == ["campaigns"] and method == "GET":
            if not self._facility_allowed(identity, headers, "view", "relocation", ""):
                return ApiResponse.json(403, {"error": "forbidden"})
            items = repository.campaigns()
            return ApiResponse.json(200, {"items": items, "count": len(items)})
        if parts == ["campaigns"] and method == "POST":
            if not self._facility_allowed(identity, headers, "create", "relocation", ""):
                return ApiResponse.json(403, {"error": "forbidden"})
            try:
                data = self._json_object(body)
                item = repository.create_campaign(
                    name=str(data["name"]),
                    actor=identity.identity_id,
                    plan_id=str(data["plan_id"]),
                    scheduled_start=str(data.get("scheduled_start", "")),
                    scheduled_end=str(data.get("scheduled_end", "")),
                    notes=str(data.get("notes", "")),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_relocation_campaign"})
            return ApiResponse.json(201, {"campaign": item})
        if len(parts) == 2 and parts[0] == "campaigns" and method == "GET":
            if not self._facility_allowed(
                identity, headers, "view", "relocation", parts[1]
            ):
                return ApiResponse.json(404, {"error": "not_found"})
            item = repository.campaign(parts[1])
            return (
                ApiResponse.json(200, {"campaign": item})
                if item is not None
                else ApiResponse.json(404, {"error": "not_found"})
            )
        if len(parts) == 2 and parts[0] == "steps" and method == "GET":
            if not self._facility_allowed(identity, headers, "view", "relocation", parts[1]):
                return ApiResponse.json(404, {"error": "not_found"})
            item = repository.step(parts[1])
            return (
                ApiResponse.json(200, {"step": item})
                if item is not None
                else ApiResponse.json(404, {"error": "not_found"})
            )
        if (
            len(parts) == 3
            and parts[0] == "steps"
            and parts[2] == "state"
            and method == "POST"
        ):
            if not self._facility_allowed(
                identity, headers, "update", "relocation", parts[1]
            ):
                return ApiResponse.json(403, {"error": "forbidden"})
            try:
                data = self._json_object(body)
                item = repository.transition_step(
                    parts[1],
                    str(data["state"]),
                    actor=identity.identity_id,
                    notes=str(data.get("notes", "")),
                    evidence_library_asset_id=str(
                        data.get("evidence_library_asset_id", "")
                    ),
                )
            except KeyError:
                return ApiResponse.json(404, {"error": "not_found"})
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                return ApiResponse.json(
                    409, {"error": "invalid_relocation_transition", "detail": str(exc)}
                )
            return ApiResponse.json(200, {"step": item})
        return ApiResponse.json(404, {"error": "not_found"})

    def _facility_allowed(
        self,
        identity: Identity,
        headers: dict[str, str],
        action: str,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        return self._allow(
            identity,
            headers,
            action,
            f"operations.{resource_type}",
            resource_id,
            "",
            "operations",
        )

    @staticmethod
    def _json_object(body: bytes) -> dict[str, Any]:
        if len(body) > 128 * 1024:
            raise ValueError("request too large")
        value = json.loads(body or b"{}")
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value
