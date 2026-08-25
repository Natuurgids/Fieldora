"""Browser-specific governed API behavior without weakening the public API model."""

from __future__ import annotations

import json
from http.cookies import SimpleCookie
from urllib.parse import quote, unquote, urlsplit

from natureai_next.application.access_control import AccessAdministrationService
from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import (
    AccessRequest,
    PolicyEffect,
    PolicySource,
)
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_web import (
    patch_browser_functionality_response,
)
from natureai_next.server.directory_intake_web import patch_directory_intake_response
from natureai_next.server.project_owner_contract_api import ProjectOwnerContractFieldoraApi
from natureai_next.server.web_capabilities import capability_payload

_COOKIE_NAME = "fieldora_session"
_COOKIE_PATH = "/api/v1/"
_PROJECT_OWNER_RESOURCE_TYPES = (
    "project",
    "phase",
    "task",
    "sprint",
    "allocation",
    "dossier",
    "dossier_review",
    "observation",
    "specimen",
    "encounter",
    "protocol",
    "survey_event",
    "enrichment",
    "sample",
    "laboratory_record",
    "collection",
    "asset",
)


class BrowserFunctionalityFieldoraApi(ProjectOwnerContractFieldoraApi):
    """Add secure same-origin browser sessions and explicit project creation."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        routed_headers = dict(headers)
        cookie_token = _session_cookie(routed_headers.get("cookie", ""))
        if not routed_headers.get("authorization") and cookie_token:
            routed_headers["authorization"] = f"Bearer {cookie_token}"

        route = urlsplit(target)
        if route.path == "/api/v1/web/capabilities" and method == "GET":
            response = self._web_capabilities(routed_headers)
        elif route.path == "/api/v1/projects" and method == "POST":
            response = self._create_project(routed_headers, body)
        else:
            response = super().dispatch(method, target, routed_headers, body)

        response = self._browser_session_response(
            method, route.path, routed_headers, cookie_token, response
        )
        response = patch_browser_functionality_response(target, response)
        return patch_directory_intake_response(target, response)

    def _web_capabilities(self, headers: dict[str, str]) -> ApiResponse:
        """Project browser destinations from the same PBAC tuples as their APIs."""
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})
        payload = capability_payload(self, identity)
        audit = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "view_audit",
                "security_audit",
                "",
                identity.organization_id,
                "",
                "administration",
            )
        ).allowed
        pages = payload["pages"]
        assert isinstance(pages, dict)
        pages["audit"] = audit
        pages["administration"] = pages.get("administration") is True or audit
        return ApiResponse.json(200, payload)

    def _browser_session_response(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        cookie_token: str,
        response: ApiResponse,
    ) -> ApiResponse:
        if path == "/api/v1/session" and method == "DELETE":
            return _with_cookie(response, _expired_cookie())

        token = ""
        if path == "/api/v1/session" and method == "POST" and response.status < 400:
            try:
                payload = json.loads(response.body)
                token = str(payload.get("access_token", "")).strip()
            except (TypeError, ValueError, json.JSONDecodeError):
                token = ""
        elif (
            not cookie_token
            and response.status < 400
            and headers.get("x-fieldora-web-session", "") == "1"
        ):
            value = headers.get("authorization", "")
            if value.startswith("Bearer "):
                token = value[7:].strip()

        return _with_cookie(response, _session_cookie_header(token)) if token else response

    def _create_project(
        self, headers: dict[str, str], body: bytes
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
            resource_id = str(record["id"]).strip()
            name = str(record.get("name") or record.get("title") or "").strip()
            if not resource_id or not name:
                raise ValueError
            record["id"] = resource_id
            record["name"] = name
            record.setdefault("status", "active")
            record.setdefault("owner_id", identity.identity_id)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})

        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "create",
                "project",
                resource_id,
                identity.organization_id,
                "",
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})

        expected = headers.get("if-match")
        try:
            revision = self._science.put(
                "projects",
                record,
                None if expected is None else int(expected),
            )
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})

        # A creator must be able to work inside the project immediately.  This is
        # not an administrator bypass: the grant is subject-specific and constrained
        # to the new project, organization and research purpose.  Later contracts or
        # explicit denies still participate in the normal PBAC decision.
        if self._access_repository is not None:
            administration = AccessAdministrationService(self._access_repository)
            administration.create_policy(
                name=f"Project owner workspace: {name}",
                effect=PolicyEffect.ALLOW,
                source=PolicySource.OBJECT_GRANT,
                source_id=resource_id,
                subject_id=identity.identity_id,
                actions=(
                    "view",
                    "edit",
                    "upload",
                    "download",
                    "search",
                    "link",
                    "unlink",
                    "export",
                ),
                resource_types=_PROJECT_OWNER_RESOURCE_TYPES,
                organization_id=identity.organization_id,
                project_id=resource_id,
                purposes=("research",),
            )
        return ApiResponse.json(201, {"item": record, "revision": revision})


def _session_cookie(raw_cookie: str) -> str:
    if not raw_cookie:
        return ""
    cookie = SimpleCookie()
    try:
        cookie.load(raw_cookie)
    except Exception:
        return ""
    morsel = cookie.get(_COOKIE_NAME)
    return "" if morsel is None else unquote(morsel.value)


def _session_cookie_header(token: str) -> str:
    encoded = quote(token, safe="")
    return (
        f"{_COOKIE_NAME}={encoded}; Path={_COOKIE_PATH}; Secure; HttpOnly; "
        "SameSite=Strict"
    )


def _expired_cookie() -> str:
    return (
        f"{_COOKIE_NAME}=; Path={_COOKIE_PATH}; Max-Age=0; Secure; HttpOnly; "
        "SameSite=Strict"
    )


def _with_cookie(response: ApiResponse, cookie: str) -> ApiResponse:
    return ApiResponse(
        response.status,
        response.body,
        response.content_type,
        (*response.headers, ("Set-Cookie", cookie)),
    )