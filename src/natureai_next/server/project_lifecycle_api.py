"""Selected-Project capabilities and status lifecycle for the managed browser API."""

from __future__ import annotations

import json
from urllib.parse import unquote, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import (
    BrowserFunctionalityFieldoraApi,
    _session_cookie,
)
from natureai_next.server.project_lifecycle_web import patch_project_lifecycle_response


class ProjectLifecycleFieldoraApi(BrowserFunctionalityFieldoraApi):
    """Add fail-closed selected-Project lifecycle capability and status routes."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        routed_headers = dict(headers)
        cookie_token = _session_cookie(routed_headers.get("cookie", ""))
        if not routed_headers.get("authorization") and cookie_token:
            routed_headers["authorization"] = f"Bearer {cookie_token}"
        project_id, action = self._route(route.path)
        if project_id and action == "capabilities" and method == "GET":
            response = self._project_capabilities(project_id, routed_headers)
            response = self._browser_session_response(
                method, route.path, routed_headers, cookie_token, response
            )
        elif project_id and action == "status" and method == "PATCH":
            response = self._set_project_status(project_id, routed_headers, body)
            response = self._browser_session_response(
                method, route.path, routed_headers, cookie_token, response
            )
        else:
            response = super().dispatch(method, target, headers, body)
        return patch_project_lifecycle_response(target, response)

    @staticmethod
    def _route(path: str) -> tuple[str, str]:
        prefix = "/api/v1/projects/"
        if not path.startswith(prefix):
            return "", ""
        parts = path[len(prefix):].strip("/").split("/")
        if len(parts) != 2 or parts[1] not in {"capabilities", "status"}:
            return "", ""
        return unquote(parts[0]).strip(), parts[1]

    def _project_capabilities(
        self, project_id: str, headers: dict[str, str]
    ) -> ApiResponse:
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})
        current = self._project_for_organization(identity.organization_id, project_id)
        if current is None:
            return ApiResponse.json(404, {"error": "not_found"})
        purpose = headers.get("x-fieldora-purpose", "research")
        view = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "view",
                "project",
                project_id,
                identity.organization_id,
                project_id,
                purpose,
            )
        ).allowed
        if not view:
            return ApiResponse.json(404, {"error": "not_found"})
        edit = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "edit",
                "project",
                project_id,
                identity.organization_id,
                project_id,
                purpose,
            )
        ).allowed
        return ApiResponse.json(
            200,
            {"actions": {"edit": edit}, "default_deny": True},
        )

    def _set_project_status(
        self, project_id: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if self._project_management is None:
            return ApiResponse.json(404, {"error": "not_found"})
        if len(body) > 1_048_576:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed as exc:
            return ApiResponse.json(
                401, {"error": "unauthorized", "detail": str(exc)}
            )
        try:
            record = json.loads(body)
            if not isinstance(record, dict) or "expected_revision" not in record:
                raise ValueError
            expected_revision = int(record["expected_revision"])
            status = str(record["status"]).strip().casefold()
            if not status:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        current = self._project_for_organization(identity.organization_id, project_id)
        if current is None:
            return ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "edit",
                "project",
                project_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})
        setter = getattr(self._project_management, "set_project_status", None)
        if not callable(setter):
            return ApiResponse.json(501, {"error": "project_status_unavailable"})
        try:
            setter(
                project_id,
                status,
                organization_id=identity.organization_id,
                actor_id=identity.identity_id,
                expected_revision=expected_revision,
            )
        except KeyError:
            return ApiResponse.json(404, {"error": "not_found"})
        except ValueError as exc:
            if "revision conflict" in str(exc).lower():
                latest = self._project_for_organization(
                    identity.organization_id, project_id
                )
                return ApiResponse.json(
                    409,
                    {
                        "error": "revision_conflict",
                        "current": (
                            None if latest is None else self._project_item(latest)
                        ),
                    },
                )
            return ApiResponse.json(
                400, {"error": "invalid_request", "detail": str(exc)}
            )
        item = self._project_for_organization(identity.organization_id, project_id)
        assert item is not None
        return ApiResponse.json(
            200, {"item": self._project_item(item), "revision": item.revision}
        )
