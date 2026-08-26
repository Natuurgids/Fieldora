"""Selected-Project lifecycle and governed child-work routes for the managed browser API."""

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

_CHILD_ROUTES = {
    "/api/v1/phases": "phase",
    "/api/v1/tasks": "task",
    "/api/v1/sprints": "sprint",
    "/api/v1/allocations": "allocation",
}


class ProjectLifecycleFieldoraApi(BrowserFunctionalityFieldoraApi):
    """Add fail-closed Project lifecycle and authoritative child-work routes."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        routed_headers = dict(headers)
        cookie_token = _session_cookie(routed_headers.get("cookie", ""))
        if not routed_headers.get("authorization") and cookie_token:
            routed_headers["authorization"] = f"Bearer {cookie_token}"
        project_id, action = self._route(route.path)
        child_kind = _CHILD_ROUTES.get(route.path)
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
        elif child_kind and method == "GET" and self._project_management is not None:
            response = self._managed_children(child_kind, routed_headers)
            response = self._browser_session_response(
                method, route.path, routed_headers, cookie_token, response
            )
        elif child_kind and method == "POST" and self._project_management is not None:
            response = self._create_managed_child(child_kind, routed_headers, body)
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

    def _managed_children(
        self, kind: str, headers: dict[str, str]
    ) -> ApiResponse:
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})
        assert self._project_management is not None
        getter = getattr(self._project_management, f"{kind}s", None)
        if not callable(getter):
            return ApiResponse.json(501, {"error": f"project_{kind}_unavailable"})
        purpose = headers.get("x-fieldora-purpose", "research")
        items: list[dict[str, object]] = []
        for item in getter(identity.organization_id):
            project_id = str(item.get("project_id", "")).strip()
            resource_id = str(item.get("id", "")).strip()
            if not project_id or not resource_id:
                continue
            decision = self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "view",
                    kind,
                    resource_id,
                    identity.organization_id,
                    project_id,
                    purpose,
                )
            )
            if decision.allowed:
                items.append(item)
        return ApiResponse.json(200, {"items": items})

    @staticmethod
    def _record_date(record: dict[str, object], primary: str, fallback: str) -> str:
        value = str(record.get(primary) or record.get(fallback) or "").strip()
        if "T" in value:
            return value.split("T", 1)[0]
        return value

    def _create_managed_child(
        self, kind: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
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
            if not isinstance(record, dict):
                raise ValueError
            project_id = str(record["project_id"]).strip()
            if not project_id:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        current = self._project_for_organization(identity.organization_id, project_id)
        if current is None:
            return ApiResponse.json(404, {"error": "not_found"})
        action = "manage" if kind == "allocation" else "edit"
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                "project",
                project_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})
        assert self._project_management is not None
        try:
            child_id = self._persist_child(
                kind,
                project_id,
                identity.organization_id,
                identity.identity_id,
                record,
            )
        except KeyError:
            return ApiResponse.json(404, {"error": "not_found"})
        except ValueError as exc:
            return ApiResponse.json(
                400, {"error": "invalid_request", "detail": str(exc)}
            )
        getter = getattr(self._project_management, f"{kind}s")
        item = next(
            (
                child
                for child in getter(identity.organization_id)
                if str(child.get("id", "")) == child_id
            ),
            None,
        )
        if item is None:
            return ApiResponse.json(500, {"error": "project_child_refresh_failed"})
        return ApiResponse.json(201, {"item": item})

    def _persist_child(
        self,
        kind: str,
        project_id: str,
        organization_id: str,
        actor_id: str,
        record: dict[str, object],
    ) -> str:
        assert self._project_management is not None
        name = str(record.get("name") or record.get("title") or "").strip()
        description = str(record.get("description", "")).strip()
        if kind == "phase":
            return self._project_management.create_phase(
                project_id,
                name,
                organization_id=organization_id,
                actor_id=actor_id,
                description=description,
                planned_budget=float(record.get("planned_budget") or 0),
                realized_budget=float(record.get("realized_budget") or 0),
            )
        if kind == "sprint":
            return self._project_management.create_sprint(
                project_id,
                name,
                organization_id=organization_id,
                actor_id=actor_id,
                start_date=self._record_date(record, "start_date", "starts_at"),
                end_date=self._record_date(record, "end_date", "ends_at"),
                goal=str(record.get("goal") or description).strip(),
            )
        if kind == "task":
            return self._project_management.create_task(
                project_id,
                name,
                organization_id=organization_id,
                actor_id=actor_id,
                parent_task_id=str(record.get("parent_task_id") or "").strip() or None,
                phase_id=str(record.get("phase_id") or "").strip() or None,
                sprint_id=str(record.get("sprint_id") or "").strip() or None,
                owner_id=str(record.get("assignee_id") or record.get("owner_id") or "").strip(),
                description=description,
                priority=str(record.get("priority") or "normal").strip(),
                start_date=self._record_date(record, "start_date", "starts_at"),
                due_date=self._record_date(record, "due_date", "ends_at"),
                estimate_hours=float(record.get("manual_estimate") or record.get("estimate_hours") or 0),
                realized_hours=float(record.get("realized") or record.get("realized_hours") or 0),
            )
        if kind == "allocation":
            return self._project_management.create_allocation(
                project_id,
                str(record.get("user_id") or "").strip(),
                organization_id=organization_id,
                actor_id=actor_id,
                start_date=self._record_date(record, "start_date", "starts_at"),
                end_date=self._record_date(record, "end_date", "ends_at"),
                hours_per_week=float(record.get("hours_per_week") or 0),
                allocation_percent=float(record.get("allocation_percent") or 0),
                role=str(record.get("role") or description).strip(),
                phase_id=str(record.get("phase_id") or "").strip() or None,
            )
        raise ValueError("unsupported Project child type")

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
