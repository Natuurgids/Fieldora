"""Authorization-safe pagination for managed browser list surfaces."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.parse import parse_qs, quote, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import _session_cookie
from natureai_next.server.pagination import (
    scan_audit,
    scan_media,
    scan_projects,
    scan_science,
)

_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 100


class PaginationApiMixin:
    """Serve bounded Library, Projects, Observations, and Audit pages.

    The persistence scanners fetch bounded candidate chunks. PBAC filtering happens
    before a cursor is disclosed, so denied rows cannot inflate ``count`` or create a
    ``next_cursor`` signal on their own.
    """

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        if route.path == "/app.js" and method == "GET":
            return patch_pagination_web_response(
                target, super().dispatch(method, target, headers, body)
            )
        if method != "GET" or route.path not in {
            "/api/v1/projects",
            "/api/v1/observations",
            "/api/v1/media",
            "/api/v1/audit",
        }:
            return super().dispatch(method, target, headers, body)
        if route.path == "/api/v1/media" and parse_qs(route.query).get("project_id"):
            # Project-associated media has additional relationship semantics in the
            # established browser adapter. WEB-047 covers the top-level Library list.
            return super().dispatch(method, target, headers, body)

        routed_headers = dict(headers)
        cookie_token = _session_cookie(routed_headers.get("cookie", ""))
        if not routed_headers.get("authorization") and cookie_token:
            routed_headers["authorization"] = f"Bearer {cookie_token}"

        # Reuse the established dispatch chain for authentication, lifecycle, tenant
        # quota, and service gates without invoking the list read itself.
        gate = super().dispatch("DELETE", route.path, routed_headers, b"")
        if gate.status != 404:
            return gate
        try:
            _token, identity = self._identity(routed_headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})
        try:
            limit, after = _page_request(route.query)
            if route.path == "/api/v1/projects":
                return self._paged_projects(identity, routed_headers, limit, after)
            if route.path == "/api/v1/observations":
                return self._paged_observations(identity, routed_headers, limit, after)
            if route.path == "/api/v1/media":
                return self._paged_media(identity, routed_headers, limit, after)
            return self._paged_audit(identity, routed_headers, limit, after)
        except ValueError as exc:
            error = "invalid_cursor" if str(exc) == "invalid_cursor" else "invalid_limit"
            return ApiResponse.json(400, {"error": error})

    def _paged_projects(self, identity, headers, limit: int, after: str) -> ApiResponse:
        purpose = headers.get("x-fieldora-purpose", "research")
        service = getattr(self, "_project_management", None)
        scanner: Callable[[str, int], tuple]
        if service is not None:
            scanner = lambda cursor, size: scan_projects(
                service, identity.organization_id, cursor, size
            )
        else:
            scanner = lambda cursor, size: scan_science(
                self._science, "projects", cursor, size
            )

        def allowed(item: dict) -> bool:
            project_id = str(item.get("id", ""))
            return self._decisions.decide(
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

        return _authorized_page(scanner, allowed, limit, after)

    def _paged_observations(
        self, identity, headers, limit: int, after: str
    ) -> ApiResponse:
        purpose = headers.get("x-fieldora-purpose", "research")

        def allowed(item: dict) -> bool:
            return self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "view",
                    "observation",
                    str(item.get("id", "")),
                    identity.organization_id,
                    str(item.get("project_id", "")),
                    purpose,
                )
            ).allowed

        return _authorized_page(
            lambda cursor, size: scan_science(
                self._science, "server_observations", cursor, size
            ),
            allowed,
            limit,
            after,
        )

    def _paged_media(self, identity, headers, limit: int, after: str) -> ApiResponse:
        if self._media is None:
            return ApiResponse.json(404, {"error": "not_found"})
        purpose = headers.get("x-fieldora-purpose", "research")

        def allowed(record) -> bool:
            return self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "view",
                    "asset",
                    record.media_id,
                    record.organization_id,
                    record.project_id,
                    purpose,
                )
            ).allowed

        response = _authorized_page(
            lambda cursor, size: scan_media(
                self._media, identity.organization_id, "", cursor, size
            ),
            allowed,
            limit,
            after,
            transform=lambda record: {
                "media_id": record.media_id,
                "project_id": record.project_id,
                "mime_type": record.mime_type,
                "size_bytes": record.size_bytes,
                "sha256": record.sha256,
                "download_url": f"/api/v1/media/{quote(record.media_id)}",
            },
        )
        return response

    def _paged_audit(self, identity, headers, limit: int, after: str) -> ApiResponse:
        if self._audit_repository is None:
            return ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "view_audit",
                "security_audit",
                "",
                identity.organization_id,
                "",
                headers.get("x-fieldora-purpose", "administration"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})

        platform_admin = identity.attributes.get("platform_admin") == "true"

        def allowed(event) -> bool:
            request = json.loads(str(event["request_json"]))
            return platform_admin or request.get("organization_id") == identity.organization_id

        response = _authorized_page(
            lambda cursor, size: scan_audit(
                self._audit_repository, cursor, size
            ),
            allowed,
            limit,
            after,
            transform=lambda event: {
                "sequence": event["sequence"],
                "occurred_at_utc": event["occurred_at_utc"],
                "subject_id": event["subject_id"],
                "action": event["action"],
                "resource_type": event["resource_type"],
                "resource_id": event["resource_id"],
                "allowed": bool(event["allowed"]),
                "reason": event["reason"],
                "policy_ids": json.loads(str(event["policy_ids_json"])),
            },
        )
        payload = json.loads(response.body)
        verified, detail = self._audit_repository.verify_audit_chain()
        payload["chain_verified"] = verified
        payload["chain_detail"] = detail
        return ApiResponse.json(200, payload)


def _page_request(query_string: str) -> tuple[int, str]:
    query = parse_qs(query_string)
    try:
        limit = int(query.get("limit", [str(_PAGE_SIZE)])[0])
    except ValueError as exc:
        raise ValueError("invalid_limit") from exc
    if not 1 <= limit <= _MAX_PAGE_SIZE:
        raise ValueError("invalid_limit")
    return limit, query.get("after", [""])[0]


def _authorized_page(
    scanner: Callable[[str, int], tuple],
    allowed: Callable[[object], bool],
    limit: int,
    after: str,
    *,
    transform: Callable[[object], object] | None = None,
) -> ApiResponse:
    authorized: list[tuple[object, str]] = []
    scan_cursor = after
    while len(authorized) <= limit:
        batch_size = max(25, min(_MAX_PAGE_SIZE, limit + 1 - len(authorized)))
        candidates = scanner(scan_cursor, batch_size)
        if not candidates:
            break
        for item, cursor in candidates:
            scan_cursor = cursor
            if allowed(item):
                authorized.append((item, cursor))
                if len(authorized) > limit:
                    break
        if len(authorized) > limit or len(candidates) < batch_size:
            break

    disclosed = authorized[:limit]
    mapper = transform or (lambda item: item)
    items = [mapper(item) for item, _cursor_value in disclosed]
    next_cursor = disclosed[-1][1] if len(authorized) > limit and disclosed else ""
    return ApiResponse.json(
        200,
        {"items": items, "count": len(items), "next_cursor": next_cursor},
    )


_PAGINATION_WEB_PATCH = bytes(
    r"""

/* WEB-047 bounded list pagination. */
(()=>{
 if(window.__fieldoraPaginationWired)return;
 window.__fieldoraPaginationWired=true;
 const pageSize=50;
 let projectCursor="",mediaCursor="",observationCursor="",auditCursor="",auditEvents=[];
 const pager=(target,id,cursor,handler)=>{
  const node=q(target);if(!node)return;
  let button=q(id);if(!button){button=document.createElement("button");button.id=id;button.textContent="Load more";button.className="section";node.insertAdjacentElement("afterend",button)}
  button.hidden=!cursor;button.onclick=handler;
 };
 const loadProjectPage=async(reset=true)=>{
  const result=await api(`/api/v1/projects?limit=${pageSize}${!reset&&projectCursor?`&after=${encodeURIComponent(projectCursor)}`:""}`);
  projects=reset?(result.items||[]):[...projects,...(result.items||[])];projectCursor=result.next_cursor||"";projectOptions();
  pager("portfolio-list","projects-load-more",projectCursor,()=>loadProjectPage(false).then(loadPortfolio));
 };
 loadBase=async()=>{me=await api("/api/v1/me");await loadProjectPage(true);q("contract-org").value=me.organization_id;q("device-org").value=me.organization_id;await loadHome();q("login").hidden=true;q("workspace").hidden=false;q("footer-state").textContent=`${me.display_name} · ${me.organization_id} · up to date`};
 loadMedia=async(reset=true)=>{try{const result=await api(`/api/v1/media?limit=${pageSize}${!reset&&mediaCursor?`&after=${encodeURIComponent(mediaCursor)}`:""}`);media=reset?(result.items||[]):[...media,...(result.items||[])];mediaCursor=result.next_cursor||"";renderMedia();pager("media-grid","media-load-more",mediaCursor,()=>loadMedia(false))}catch(e){cards("media-grid",[],x=>x,e.message)}};
 loadObservations=async(reset=true)=>{try{const result=await api(`/api/v1/observations?limit=${pageSize}${!reset&&observationCursor?`&after=${encodeURIComponent(observationCursor)}`:""}`);observations=reset?(result.items||[]):[...observations,...(result.items||[])];observationCursor=result.next_cursor||"";renderObservations();pager("observation-list","observations-load-more",observationCursor,()=>loadObservations(false))}catch(e){cards("observation-list",[],x=>x,e.message)}};
 const renderAudit=verified=>{cards("audit-list",auditEvents,a=>`<div><strong>${esc(a.action)}</strong> · ${esc(a.resource_type)}<br><span class="muted">${esc(a.subject_id)} · ${esc(a.occurred_at_utc)} · ${a.allowed?"allowed":"denied"}</span></div>`);q("audit-list").insertAdjacentHTML("afterbegin",`<p class="accent">Audit chain ${verified?"verified":"failed"}</p>`)};
 loadAudit=async(reset=true)=>{try{const result=await api(`/api/v1/audit?limit=25${!reset&&auditCursor?`&after=${encodeURIComponent(auditCursor)}`:""}`,{purpose:"administration"});auditEvents=reset?(result.items||[]):[...auditEvents,...(result.items||[])];auditCursor=result.next_cursor||"";renderAudit(result.chain_verified);pager("audit-list","audit-load-more",auditCursor,()=>loadAudit(false))}catch(e){cards("audit-list",[],x=>x,e.message)}};
})();
""",
    "utf-8",
)


def patch_pagination_web_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _PAGINATION_WEB_PATCH in response.body
    ):
        return response
    body = response.body
    body = body.replace(
        b'api("/api/v1/projects")', b'api("/api/v1/projects?limit=50")'
    )
    body = body.replace(
        b'api("/api/v1/media?limit=500")', b'api("/api/v1/media?limit=50")'
    )
    body = body.replace(
        b'api("/api/v1/observations")', b'api("/api/v1/observations?limit=50")'
    )
    body = body.replace(
        b'if(token)loadBase().catch(()=>{sessionStorage.clear();token=""});',
        b'if(token)setTimeout(()=>loadBase().catch(()=>{sessionStorage.clear();token=""}),0);',
    )
    return ApiResponse(
        response.status,
        body + _PAGINATION_WEB_PATCH,
        response.content_type,
        response.headers,
    )
