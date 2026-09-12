"""Server-side governed filtering for large managed-browser collections."""

from __future__ import annotations

import sqlite3
from urllib.parse import parse_qs, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import _session_cookie
from natureai_next.server.media import MediaRecord
from natureai_next.server.pagination import _cursor, _decode, _payload
from natureai_next.server.pagination_api import _authorized_page, _page_request

_MAX_QUERY = 200
_ALLOWED_MEDIA_KINDS = {"image", "audio", "video", "application"}
_ALLOWED_OBSERVATION_FILTERS = {
    "confirmed": ("confirmed",),
    "review": ("needs_review", "deferred"),
    "disputed": ("disputed",),
}


class FilteringApiMixin:
    """Apply search/filter predicates before PBAC projection and pagination."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        if route.path == "/app.js" and method == "GET":
            return patch_filtering_web_response(
                target, super().dispatch(method, target, headers, body)
            )
        if method != "GET" or route.path not in {
            "/api/v1/media",
            "/api/v1/observations",
        }:
            return super().dispatch(method, target, headers, body)

        query = parse_qs(route.query)
        if route.path == "/api/v1/media":
            if query.get("project_id") or not (
                query.get("q") or query.get("kind")
            ):
                return super().dispatch(method, target, headers, body)
        elif not (query.get("q") or query.get("status")):
            return super().dispatch(method, target, headers, body)

        routed_headers = dict(headers)
        cookie_token = _session_cookie(routed_headers.get("cookie", ""))
        if not routed_headers.get("authorization") and cookie_token:
            routed_headers["authorization"] = f"Bearer {cookie_token}"
        gate = super().dispatch("DELETE", route.path, routed_headers, b"")
        if gate.status != 404:
            return gate
        try:
            _token, identity = self._identity(routed_headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})
        try:
            limit, after = _page_request(route.query)
            text = _query_text(query)
            if route.path == "/api/v1/media":
                return self._filtered_media(
                    identity,
                    routed_headers,
                    limit,
                    after,
                    text,
                    _media_kind(query),
                )
            return self._filtered_observations(
                identity,
                routed_headers,
                limit,
                after,
                text,
                _observation_statuses(query),
            )
        except ValueError as exc:
            error = str(exc)
            if error not in {
                "invalid_cursor",
                "invalid_limit",
                "invalid_query",
                "invalid_filter",
            }:
                error = "invalid_filter"
            return ApiResponse.json(400, {"error": error})

    def _filtered_media(
        self,
        identity,
        headers: dict[str, str],
        limit: int,
        after: str,
        text: str,
        kind: str,
    ) -> ApiResponse:
        if self._media is None:
            return ApiResponse.json(404, {"error": "not_found"})
        purpose = headers.get("x-fieldora-purpose", "research")

        def allowed(record: MediaRecord) -> bool:
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

        return _authorized_page(
            lambda cursor, size: _scan_media(
                self._media,
                identity.organization_id,
                cursor,
                size,
                text,
                kind,
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
                "download_url": f"/api/v1/media/{record.media_id}",
            },
        )

    def _filtered_observations(
        self,
        identity,
        headers: dict[str, str],
        limit: int,
        after: str,
        text: str,
        statuses: tuple[str, ...],
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
            lambda cursor, size: _scan_observations(
                self._science, cursor, size, text, statuses
            ),
            allowed,
            limit,
            after,
        )


def _query_text(query: dict[str, list[str]]) -> str:
    text = query.get("q", [""])[0].strip().casefold()
    if len(text) > _MAX_QUERY:
        raise ValueError("invalid_query")
    return text


def _media_kind(query: dict[str, list[str]]) -> str:
    kind = query.get("kind", [""])[0].strip().casefold()
    if kind in {"", "all"}:
        return ""
    if kind not in _ALLOWED_MEDIA_KINDS:
        raise ValueError("invalid_filter")
    return kind


def _observation_statuses(query: dict[str, list[str]]) -> tuple[str, ...]:
    status = query.get("status", [""])[0].strip().casefold()
    if status in {"", "all"}:
        return ()
    try:
        return _ALLOWED_OBSERVATION_FILTERS[status]
    except KeyError as exc:
        raise ValueError("invalid_filter") from exc


def _scan_media(
    store: object,
    organization_id: str,
    after: str,
    limit: int,
    text: str,
    kind: str,
) -> tuple[tuple[MediaRecord, str], ...]:
    position = _decode(after, "media", 1)
    media_id = str(position[0]) if position else ""
    clauses = ["organization_id={placeholder}"]
    values: list[object] = [organization_id]
    if media_id:
        clauses.append("media_id<{placeholder}")
        values.append(media_id)
    if kind:
        clauses.append("mime_type LIKE {placeholder}")
        values.append(f"{kind}/%")
    if text:
        clauses.append(
            "LOWER(media_id || ' ' || project_id || ' ' || mime_type || ' ' || sha256) "
            "LIKE {placeholder}"
        )
        values.append(f"%{text}%")

    metadata = getattr(store, "_metadata", None)
    connect = None if metadata is None else getattr(metadata, "_connect", None)
    if connect is not None:
        where = " AND ".join(clause.format(placeholder="%s") for clause in clauses)
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT media_id,relative_path,organization_id,project_id,mime_type,"
                    "size_bytes,sha256 FROM governed_media WHERE "
                    + where
                    + " ORDER BY media_id DESC LIMIT %s",
                    (*values, limit),
                )
                rows = cursor.fetchall()
        return tuple(
            (MediaRecord(*row), _cursor("media", str(row[0]))) for row in rows
        )

    database_path = getattr(store, "_database_path", None)
    if database_path is None:
        return ()
    where = " AND ".join(clause.format(placeholder="?") for clause in clauses)
    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            "SELECT * FROM governed_media WHERE "
            + where
            + " ORDER BY media_id DESC LIMIT ?",
            (*values, limit),
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        (MediaRecord(*row), _cursor("media", str(row[0]))) for row in rows
    )


def _scan_observations(
    science: object,
    after: str,
    limit: int,
    text: str,
    statuses: tuple[str, ...],
) -> tuple[tuple[dict, str], ...]:
    collection = "server_observations"
    position = _decode(after, f"science:{collection}", 2)
    clauses = ["collection_name={placeholder}"]
    values: list[object] = [collection]
    if position:
        updated_at_us, record_id = int(position[0]), str(position[1])
        clauses.append(
            "(updated_at_us>{placeholder} OR "
            "(updated_at_us={placeholder} AND record_id>{placeholder}))"
        )
        values.extend((updated_at_us, updated_at_us, record_id))
    if text:
        clauses.append("LOWER(payload_json_text) LIKE {placeholder}")
        values.append(f"%{text}%")

    database_path = getattr(science, "_database_path", None)
    if database_path is not None:
        sqlite_clauses = [
            clause.replace("payload_json_text", "payload_json").format(placeholder="?")
            for clause in clauses
        ]
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            sqlite_clauses.append(f"json_extract(payload_json,'$.status') IN ({placeholders})")
            values.extend(statuses)
        connection = sqlite3.connect(database_path)
        try:
            rows = connection.execute(
                "SELECT payload_json,updated_at_us,record_id FROM science_records WHERE "
                + " AND ".join(sqlite_clauses)
                + " ORDER BY updated_at_us,record_id LIMIT ?",
                (*values, limit),
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            (
                _payload(row[0]),
                _cursor(f"science:{collection}", int(row[1]), str(row[2])),
            )
            for row in rows
        )

    connect = getattr(science, "_connect", None)
    if connect is None:
        return ()
    postgres_clauses = [
        clause.replace("payload_json_text", "payload_json::text").format(placeholder="%s")
        for clause in clauses
    ]
    postgres_values = list(values)
    if statuses:
        placeholders = ",".join("%s" for _ in statuses)
        postgres_clauses.append(f"payload_json->>'status' IN ({placeholders})")
        postgres_values.extend(statuses)
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload_json,updated_at_us,record_id FROM science_records WHERE "
                + " AND ".join(postgres_clauses)
                + " ORDER BY updated_at_us,record_id LIMIT %s",
                (*postgres_values, limit),
            )
            rows = cursor.fetchall()
    return tuple(
        (
            _payload(row[0]),
            _cursor(f"science:{collection}", int(row[1]), str(row[2])),
        )
        for row in rows
    )


_FILTERING_WEB_PATCH = bytes(
    r"""

/* WEB-048 server-side governed collection filters. */
(()=>{
 if(window.__fieldoraFilteringWired)return;
 window.__fieldoraFilteringWired=true;
 const pageSize=50;
 let filteredMediaCursor="",filteredObservationCursor="";
 const filterPager=(target,id,cursor,handler)=>{
  const node=q(target);if(!node)return;
  let button=q(id);if(!button){button=document.createElement("button");button.id=id;button.textContent="Load more";button.className="section";node.insertAdjacentElement("afterend",button)}
  button.hidden=!cursor;button.onclick=handler;
 };
 const queryValue=selector=>(document.querySelector(selector)?.value||"").trim();
 loadMedia=async(reset=true)=>{try{
  const search=queryValue("#page-library .global-search"),kind=mediaFilter==="all"?"":mediaFilter;
  const params=new URLSearchParams({limit:String(pageSize)});if(search)params.set("q",search);if(kind)params.set("kind",kind);if(!reset&&filteredMediaCursor)params.set("after",filteredMediaCursor);
  const result=await api(`/api/v1/media?${params}`);media=reset?(result.items||[]):[...media,...(result.items||[])];filteredMediaCursor=result.next_cursor||"";renderMedia();filterPager("media-grid","media-load-more",filteredMediaCursor,()=>loadMedia(false));
 }catch(e){cards("media-grid",[],x=>x,e.message)}};
 loadObservations=async(reset=true)=>{try{
  const search=queryValue("#page-observations .global-search"),statusValue=observationFilter==="all"?"":observationFilter;
  const params=new URLSearchParams({limit:String(pageSize)});if(search)params.set("q",search);if(statusValue)params.set("status",statusValue);if(!reset&&filteredObservationCursor)params.set("after",filteredObservationCursor);
  const result=await api(`/api/v1/observations?${params}`);observations=reset?(result.items||[]):[...observations,...(result.items||[])];filteredObservationCursor=result.next_cursor||"";renderObservations();filterPager("observation-list","observations-load-more",filteredObservationCursor,()=>loadObservations(false));
 }catch(e){cards("observation-list",[],x=>x,e.message)}};
 document.querySelectorAll("[data-media-filter]").forEach(b=>b.onclick=()=>{mediaFilter=b.dataset.mediaFilter;document.querySelectorAll("[data-media-filter]").forEach(x=>x.classList.toggle("primary",x===b));loadMedia(true)});
 document.querySelectorAll("[data-observation-filter]").forEach(b=>b.onclick=()=>{observationFilter=b.dataset.observationFilter;document.querySelectorAll("[data-observation-filter]").forEach(x=>x.classList.toggle("primary",x===b));loadObservations(true)});
 let searchTimer=0;document.querySelectorAll(".global-search").forEach(input=>input.oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{if(!q("page-library").hidden)loadMedia(true);if(!q("page-observations").hidden)loadObservations(true)},150)});
})();
""",
    "utf-8",
)


def patch_filtering_web_response(target: str, response: ApiResponse) -> ApiResponse:
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _FILTERING_WEB_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _FILTERING_WEB_PATCH,
        response.content_type,
        response.headers,
    )
