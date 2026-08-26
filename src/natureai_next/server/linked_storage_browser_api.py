"""Browser composition for governed linked-storage Library and Operator surfaces."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_api import _session_cookie
from natureai_next.server.linked_storage_operator_web import (
    patch_linked_storage_operator_web_response,
)
from natureai_next.server.linked_storage_web import patch_linked_storage_web_response
from natureai_next.server.media_detail_web import patch_media_detail_response
from natureai_next.server.project_lifecycle_api import ProjectLifecycleFieldoraApi


class LinkedStorageBrowserFieldoraApi(ProjectLifecycleFieldoraApi):
    """Append linked-storage and governed Library detail browser behavior."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        media_id = self._media_detail_id(route.path)
        if media_id and method == "GET":
            routed_headers = dict(headers)
            cookie_token = _session_cookie(routed_headers.get("cookie", ""))
            if not routed_headers.get("authorization") and cookie_token:
                routed_headers["authorization"] = f"Bearer {cookie_token}"
            response = self._media_detail_response(
                media_id, route.query, routed_headers
            )
            return self._browser_session_response(
                method, route.path, routed_headers, cookie_token, response
            )

        direct_media_id = self._managed_media_id(route.path)
        try:
            response = super().dispatch(method, target, headers, body)
        except FileNotFoundError:
            if direct_media_id and method in {"GET", "HEAD"}:
                return ApiResponse.json(404, {"error": "not_found"})
            raise
        if (
            direct_media_id
            and method in {"GET", "HEAD"}
            and response.status < 400
            and self._media is not None
            and not any(
                instance.storage_kind == "managed"
                for instance in self._media.instances(
                    direct_media_id,
                    (self._media.record(direct_media_id) or _MissingMedia()).organization_id,
                )
            )
        ):
            response = ApiResponse.json(404, {"error": "not_found"})
        response = patch_linked_storage_web_response(target, response)
        response = patch_linked_storage_operator_web_response(target, response)
        return patch_media_detail_response(target, response)

    @staticmethod
    def _media_detail_id(path: str) -> str:
        prefix = "/api/v1/media/"
        suffix = "/detail"
        if not path.startswith(prefix) or not path.endswith(suffix):
            return ""
        media_id = unquote(path[len(prefix) : -len(suffix)]).strip("/")
        return media_id if media_id and "/" not in media_id else ""

    @staticmethod
    def _managed_media_id(path: str) -> str:
        prefix = "/api/v1/media/"
        if not path.startswith(prefix):
            return ""
        media_id = unquote(path[len(prefix) :]).strip("/")
        return media_id if media_id and "/" not in media_id else ""

    def _media_detail_response(
        self, media_id: str, query_string: str, headers: dict[str, str]
    ) -> ApiResponse:
        if self._media is None:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})

        record = self._media.record(media_id)
        if record is None or record.organization_id != identity.organization_id:
            return ApiResponse.json(404, {"error": "not_found"})

        project_id = parse_qs(query_string).get("project_id", [""])[0].strip()
        if project_id:
            linked_ids = set(
                self._media.associations.linked_media_ids(
                    identity.organization_id, "project", project_id
                )
            )
            if record.project_id != project_id and media_id not in linked_ids:
                return ApiResponse.json(404, {"error": "not_found"})
        else:
            project_id = record.project_id

        purpose = headers.get("x-fieldora-purpose", "research")
        view = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "view",
                "asset",
                media_id,
                record.organization_id,
                project_id,
                purpose,
            )
        )
        if not view.allowed:
            return ApiResponse.json(404, {"error": "not_found"})

        associations: list[dict[str, object]] = []
        for link in self._media.associations.links(
            media_id, identity.organization_id
        ):
            relationship_project = (
                link.target_id if link.association_type == "project" else project_id
            )
            relationship = self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "view",
                    link.association_type,
                    link.target_id,
                    identity.organization_id,
                    relationship_project,
                    link.purpose or purpose,
                )
            )
            if not relationship.allowed:
                continue
            associations.append(
                {
                    "association_type": link.association_type,
                    "target_id": link.target_id,
                    "purpose": link.purpose,
                    "linked_by": link.linked_by,
                    "linked_at_epoch": link.linked_at_epoch,
                }
            )

        instances = self._media.instances(media_id, identity.organization_id)
        if not instances:
            return ApiResponse.json(404, {"error": "not_found"})
        managed_count = sum(
            instance.storage_kind == "managed" for instance in instances
        )
        referenced_count = sum(
            instance.storage_kind == "referenced" for instance in instances
        )
        if managed_count and referenced_count:
            storage_policy = "hybrid"
        elif referenced_count:
            storage_policy = "referenced"
        else:
            storage_policy = "managed"
        storage = {
            "storage_policy": storage_policy,
            "managed_instances": managed_count,
            "referenced_instances": referenced_count,
            "available_instances": sum(
                instance.availability == "available" for instance in instances
            ),
        }

        return ApiResponse.json(
            200,
            {
                "item": {
                    "media_id": record.media_id,
                    "mime_type": record.mime_type,
                    "size_bytes": record.size_bytes,
                    "sha256": record.sha256,
                },
                "storage": storage,
                "associations": associations,
            },
        )


class _MissingMedia:
    organization_id = ""
