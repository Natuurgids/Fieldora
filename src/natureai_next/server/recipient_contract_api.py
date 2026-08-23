"""Recipient-side access bridge for source-owned governed evidence.

Sharing never transfers provenance or ownership. The media record remains in the source
organization/project. A recipient must satisfy both the source-side data contract and
normal PBAC authority inside the recipient organization/project scope.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from natureai_next.domain.access_control import AccessRequest, Identity
from natureai_next.server.api import ApiResponse
from natureai_next.server.runtime_api import RuntimeGovernedFieldoraApi


class RecipientContractFieldoraApi(RuntimeGovernedFieldoraApi):
    """Expose explicitly shared evidence without rewriting its source ownership."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        if self._barriers is None or self._media is None:
            return response

        route = urlsplit(target)
        path = route.path
        if method == "GET" and path == "/api/v1/media" and response.status == 200:
            return self._augment_media_list(response, route.query, headers)
        if (
            method in {"GET", "HEAD"}
            and path.startswith("/api/v1/media/")
            and response.status == 404
        ):
            return self._shared_media_response(
                path.removeprefix("/api/v1/media/"), method, headers
            )
        if method == "GET" and path == "/api/v1/search" and response.status == 200:
            return self._augment_search(response, route.query, headers)
        return response

    def _augment_media_list(
        self,
        response: ApiResponse,
        query_string: str,
        headers: dict[str, str],
    ) -> ApiResponse:
        _token, identity = self._identity(headers)
        memberships = self._project_memberships(identity.identity_id)
        payload = json.loads(response.body)
        items = list(payload.get("items", []))
        seen = {str(item.get("media_id", "")) for item in items}
        try:
            limit = max(1, min(int(parse_qs(query_string).get("limit", ["200"])[0]), 500))
        except ValueError:
            return response

        for media_id in self._barriers.candidate_shared_assets(
            organization_id=identity.organization_id,
            project_ids=memberships,
            limit=limit * 4,
        ):
            if media_id in seen:
                continue
            record = self._media.record(media_id)
            if record is None or record.organization_id == identity.organization_id:
                continue
            if not self._recipient_authorized(
                identity, headers, "view", media_id, memberships
            ):
                continue
            if not self._barriers.allows_asset(
                media_id,
                organization_id=identity.organization_id,
                project_ids=memberships,
            ):
                continue
            items.append(
                {
                    "media_id": record.media_id,
                    "project_id": record.project_id,
                    "source_organization_id": record.organization_id,
                    "source_project_id": record.project_id,
                    "shared_via_contract": True,
                    "mime_type": record.mime_type,
                    "size_bytes": record.size_bytes,
                    "sha256": record.sha256,
                    "download_url": f"/api/v1/media/{record.media_id}",
                }
            )
            seen.add(media_id)
            if len(items) >= limit:
                break
        return ApiResponse.json(200, {"items": items[:limit], "count": min(len(items), limit)})

    def _shared_media_response(
        self,
        media_id: str,
        method: str,
        headers: dict[str, str],
    ) -> ApiResponse:
        record = self._media.record(media_id)
        if record is None:
            return ApiResponse.json(404, {"error": "not_found"})
        _token, identity = self._identity(headers)
        if record.organization_id == identity.organization_id:
            return ApiResponse.json(404, {"error": "not_found"})
        memberships = self._project_memberships(identity.identity_id)
        if not self._barriers.allows_asset(
            media_id,
            organization_id=identity.organization_id,
            project_ids=memberships,
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        if not self._recipient_authorized(
            identity, headers, "download", media_id, memberships
        ):
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
            ("X-Fieldora-Source-Organization", record.organization_id),
            ("X-Fieldora-Source-Project", record.project_id),
            ("X-Fieldora-Shared-Via-Contract", "true"),
        ]
        if status == 206:
            response_headers.append(
                ("Content-Range", f"bytes {start}-{end}/{record.size_bytes}")
            )
        return ApiResponse(status, body, record.mime_type, tuple(response_headers))

    def _augment_search(
        self,
        response: ApiResponse,
        query_string: str,
        headers: dict[str, str],
    ) -> ApiResponse:
        if self._search is None:
            return response
        query = parse_qs(query_string)
        text = query.get("q", [""])[0].strip()
        try:
            limit = max(1, min(int(query.get("limit", ["25"])[0]), 100))
        except ValueError:
            return response
        if len(text) < 2 or len(text) > 500:
            return response

        _token, identity = self._identity(headers)
        memberships = self._project_memberships(identity.identity_id)
        shared_ids = set(
            self._barriers.candidate_shared_assets(
                organization_id=identity.organization_id,
                project_ids=memberships,
                limit=limit * 20,
            )
        )
        payload = json.loads(response.body)
        items = list(payload.get("items", []))
        seen = {
            (str(item.get("resource_type", "")), str(item.get("resource_id", "")))
            for item in items
        }
        for hit in self._search.candidates(text, limit * 10):
            key = (hit.resource_type, hit.resource_id)
            if key in seen or hit.resource_type != "asset" or hit.resource_id not in shared_ids:
                continue
            if hit.organization_id == identity.organization_id:
                continue
            if not self._barriers.allows_asset(
                hit.resource_id,
                organization_id=identity.organization_id,
                project_ids=memberships,
            ):
                continue
            if not self._recipient_authorized(
                identity, headers, "search", hit.resource_id, memberships
            ):
                continue
            items.append(
                {
                    "resource_type": hit.resource_type,
                    "resource_id": hit.resource_id,
                    "project_id": hit.project_id,
                    "source_organization_id": hit.organization_id,
                    "source_project_id": hit.project_id,
                    "shared_via_contract": True,
                    "title": hit.title,
                    "snippet": hit.snippet,
                }
            )
            seen.add(key)
            if len(items) >= limit:
                break
        return ApiResponse.json(200, {"items": items[:limit], "count": min(len(items), limit)})

    def _recipient_authorized(
        self,
        identity: Identity,
        headers: dict[str, str],
        action: str,
        media_id: str,
        memberships: tuple[str, ...],
    ) -> bool:
        """Require ordinary PBAC in the recipient scope named by the source contract."""
        purpose = headers.get("x-fieldora-purpose", "research")
        scopes = ("", *memberships)
        for project_id in scopes:
            decision = self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    action,
                    "asset",
                    media_id,
                    identity.organization_id,
                    project_id,
                    purpose,
                    attributes={"contract_recipient": "true"},
                )
            )
            if decision.allowed:
                return True
        return False
