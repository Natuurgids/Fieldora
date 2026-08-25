"""Browser-specific governed API behavior without weakening the public API model."""

from __future__ import annotations

import json
from collections.abc import Callable
from http.cookies import SimpleCookie
from typing import Protocol
from urllib.parse import parse_qs, quote, unquote, urlsplit

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
from natureai_next.server.media_links import new_association
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


class ProjectSummaryLike(Protocol):
    project_id: str
    organization_id: str
    name: str
    status: str
    owner_id: str
    start_date: str
    due_date: str
    budget: float
    currency: str
    description: str


class ManagedProjectService(Protocol):
    def create_project(
        self,
        name: str,
        *,
        organization_id: str,
        owner_id: str,
        actor_id: str,
        start_date: str = "",
        due_date: str = "",
        description: str = "",
        budget: float = 0,
        currency: str = "EUR",
        template_id: str | None = None,
    ) -> str: ...

    def projects(self, organization_id: str) -> tuple[ProjectSummaryLike, ...]: ...


class BrowserFunctionalityFieldoraApi(ProjectOwnerContractFieldoraApi):
    """Add secure same-origin browser sessions and explicit project creation."""

    _project_management_factory: Callable[[], ManagedProjectService] | None = None

    @classmethod
    def configure_project_management(
        cls, factory: Callable[[], ManagedProjectService] | None
    ) -> None:
        cls._project_management_factory = factory

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        factory = type(self)._project_management_factory
        self._project_management = None if factory is None else factory()

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        routed_headers = dict(headers)
        cookie_token = _session_cookie(routed_headers.get("cookie", ""))
        if not routed_headers.get("authorization") and cookie_token:
            routed_headers["authorization"] = f"Bearer {cookie_token}"

        route = urlsplit(target)
        upload_context = self._upload_context(method, route.path)
        if route.path == "/api/v1/web/capabilities" and method == "GET":
            response = self._web_capabilities(routed_headers)
        elif (
            route.path == "/api/v1/projects"
            and method == "GET"
            and self._project_management is not None
        ):
            response = self._managed_projects(routed_headers)
        elif route.path == "/api/v1/projects" and method == "POST":
            response = self._create_project(routed_headers, body)
        elif (
            route.path == "/api/v1/media"
            and method == "GET"
            and parse_qs(route.query).get("project_id", [""])[0]
        ):
            response = self._associated_media_list_response(
                route.query, routed_headers
            )
        elif (
            route.path.startswith("/api/v1/media/")
            and method in {"GET", "HEAD"}
            and parse_qs(route.query).get("project_id", [""])[0]
        ):
            response = self._associated_media_response(
                route.path.rsplit("/", 1)[-1],
                method,
                route.query,
                routed_headers,
            )
        else:
            response = super().dispatch(method, target, routed_headers, body)

        if upload_context is not None and response.status == 201:
            self._link_completed_upload(upload_context, routed_headers, response)
        response = self._browser_session_response(
            method, route.path, routed_headers, cookie_token, response
        )
        response = patch_browser_functionality_response(target, response)
        return patch_directory_intake_response(target, response)

    def _upload_context(self, method: str, path: str):
        if self._media is None or method != "PUT":
            return None
        prefix = "/api/v1/uploads/"
        if not path.startswith(prefix):
            return None
        upload_id = path[len(prefix):].strip()
        return self._media.upload(upload_id) if upload_id else None

    def _link_completed_upload(
        self, upload, headers: dict[str, str], response: ApiResponse
    ) -> None:
        if self._media is None or not upload.project_id:
            return
        try:
            payload = json.loads(response.body)
            media_id = str(payload["media_id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return
        self._media.associations.link(
            new_association(
                media_id=media_id,
                organization_id=upload.organization_id,
                association_type="project",
                target_id=upload.project_id,
                purpose=headers.get("x-fieldora-purpose", "research"),
                linked_by=upload.subject_id,
            )
        )

    def _associated_media_list_response(
        self, query_string: str, headers: dict[str, str]
    ) -> ApiResponse:
        if self._media is None:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})
        query = parse_qs(query_string)
        project_id = query.get("project_id", [""])[0].strip()
        try:
            limit = max(1, min(int(query.get("limit", ["200"])[0]), 500))
        except ValueError:
            return ApiResponse.json(400, {"error": "invalid_limit"})
        linked_ids = set(
            self._media.associations.linked_media_ids(
                identity.organization_id, "project", project_id
            )
        )
        items: list[dict[str, object]] = []
        for record in self._media.records(identity.organization_id, "", 500):
            if record.project_id != project_id and record.media_id not in linked_ids:
                continue
            decision = self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "view",
                    "asset",
                    record.media_id,
                    record.organization_id,
                    project_id,
                    headers.get("x-fieldora-purpose", "research"),
                )
            )
            if decision.allowed:
                items.append(
                    {
                        "media_id": record.media_id,
                        "project_id": project_id,
                        "mime_type": record.mime_type,
                        "size_bytes": record.size_bytes,
                        "sha256": record.sha256,
                        "download_url": (
                            f"/api/v1/media/{record.media_id}?project_id={quote(project_id)}"
                        ),
                    }
                )
            if len(items) == limit:
                break
        return ApiResponse.json(200, {"items": items, "count": len(items)})

    def _associated_media_response(
        self,
        media_id: str,
        method: str,
        query_string: str,
        headers: dict[str, str],
    ) -> ApiResponse:
        if self._media is None:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})
        project_id = parse_qs(query_string).get("project_id", [""])[0].strip()
        record = self._media.record(media_id)
        if record is None or record.organization_id != identity.organization_id:
            return ApiResponse.json(404, {"error": "not_found"})
        linked_ids = set(
            self._media.associations.linked_media_ids(
                identity.organization_id, "project", project_id
            )
        )
        if record.project_id != project_id and media_id not in linked_ids:
            return ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "download",
                "asset",
                media_id,
                record.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(404, {"error": "not_found"})
        start, end, status = 0, record.size_bytes - 1, 200
        requested = headers.get("range", "")
        if requested:
            try:
                unit, values = requested.split("=", 1)
                first, last = values.split("-", 1)
                if unit != "bytes" or "," in values:
                    raise ValueError
                start = int(first)
                end = record.size_bytes - 1 if not last else int(last)
                if start < 0 or end < start or end >= record.size_bytes:
                    raise ValueError
                status = 206
            except ValueError:
                return ApiResponse(
                    416,
                    b"",
                    "application/json",
                    (("Content-Range", f"bytes */{record.size_bytes}"),),
                )
        body = b"" if method == "HEAD" else self._media.read_range(record, start, end)
        response_headers = [
            ("Accept-Ranges", "bytes"),
            ("Content-Length", str(end - start + 1)),
            ("ETag", f'"sha256-{record.sha256}"'),
            ("X-Content-SHA256", record.sha256),
        ]
        if status == 206:
            response_headers.append(
                ("Content-Range", f"bytes {start}-{end}/{record.size_bytes}")
            )
        return ApiResponse(status, body, record.mime_type, tuple(response_headers))

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

    def _managed_projects(self, headers: dict[str, str]) -> ApiResponse:
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})
        assert self._project_management is not None
        items: list[dict[str, object]] = []
        for project in self._project_management.projects(identity.organization_id):
            decision = self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "view",
                    "project",
                    project.project_id,
                    identity.organization_id,
                    project.project_id,
                    "research",
                )
            )
            if not decision.allowed:
                continue
            items.append(
                {
                    "id": project.project_id,
                    "name": project.name,
                    "description": project.description,
                    "status": project.status,
                    "owner_id": project.owner_id,
                    "start_date": project.start_date,
                    "due_date": project.due_date,
                    "budget": project.budget,
                    "currency": project.currency,
                }
            )
        return ApiResponse.json(200, {"items": items})

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
            name = str(record.get("name") or record.get("title") or "").strip()
            if not name:
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})

        if self._project_management is not None:
            decision = self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "create",
                    "project",
                    "",
                    identity.organization_id,
                    "",
                    headers.get("x-fieldora-purpose", "research"),
                )
            )
            if not decision.allowed:
                return ApiResponse.json(403, {"error": "forbidden"})
            try:
                project_id = self._project_management.create_project(
                    name,
                    organization_id=identity.organization_id,
                    owner_id=str(record.get("owner_id") or identity.identity_id),
                    actor_id=identity.identity_id,
                    start_date=str(record.get("start_date") or ""),
                    due_date=str(record.get("due_date") or ""),
                    description=str(record.get("description") or ""),
                    budget=float(record.get("budget") or 0),
                    currency=str(record.get("currency") or "EUR"),
                    template_id=(
                        str(record["template_id"]).strip()
                        if record.get("template_id")
                        else None
                    ),
                )
            except (TypeError, ValueError) as exc:
                return ApiResponse.json(
                    400, {"error": "invalid_request", "detail": str(exc)}
                )
            self._grant_project_owner(
                identity.identity_id,
                identity.organization_id,
                project_id,
                name,
            )
            item = next(
                project
                for project in self._project_management.projects(identity.organization_id)
                if project.project_id == project_id
            )
            return ApiResponse.json(
                201,
                {
                    "item": {
                        "id": item.project_id,
                        "name": item.name,
                        "description": item.description,
                        "status": item.status,
                        "owner_id": item.owner_id,
                        "start_date": item.start_date,
                        "due_date": item.due_date,
                        "budget": item.budget,
                        "currency": item.currency,
                    },
                    "revision": 1,
                },
            )

        # Temporary compatibility fallback for the one-node reference API. Managed
        # Fieldora configures a Project Management service and never uses this path.
        try:
            resource_id = str(record["id"]).strip()
            if not resource_id:
                raise ValueError
            record["id"] = resource_id
            record["name"] = name
            record.setdefault("status", "active")
            record.setdefault("owner_id", identity.identity_id)
        except (KeyError, TypeError, ValueError):
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
        self._grant_project_owner(
            identity.identity_id,
            identity.organization_id,
            resource_id,
            name,
        )
        return ApiResponse.json(201, {"item": record, "revision": revision})

    def _grant_project_owner(
        self,
        identity_id: str,
        organization_id: str,
        project_id: str,
        name: str,
    ) -> None:
        # A creator must be able to work inside the project immediately. This is not
        # an administrator bypass: the grant is subject-specific and constrained to
        # the new project, organization and research purpose. Explicit denies still
        # participate in the normal PBAC decision.
        if self._access_repository is None:
            return
        administration = AccessAdministrationService(self._access_repository)
        administration.create_policy(
            name=f"Project owner workspace: {name}",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.OBJECT_GRANT,
            source_id=project_id,
            subject_id=identity_id,
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
            organization_id=organization_id,
            project_id=project_id,
            purposes=("research",),
        )


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