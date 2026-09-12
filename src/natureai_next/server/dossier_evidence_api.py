"""Governed Dossier-to-Library evidence associations.

Library owns media identity and bytes. Dossiers only create/remove association records
that reference the canonical ``media_id``.
"""

from __future__ import annotations

import json
from urllib.parse import unquote, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.media_links import new_association


class DossierEvidenceApiMixin:
    """Expose fail-closed Dossier evidence association routes."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        parsed = self._dossier_media_route(route.path)
        if parsed is None:
            return super().dispatch(method, target, headers, body)
        dossier_id, media_id = parsed
        if media_id:
            if method == "DELETE":
                return self._unlink_dossier_evidence(
                    dossier_id, media_id, headers
                )
            return ApiResponse.json(405, {"error": "method_not_allowed"})
        if method == "GET":
            return self._dossier_evidence(dossier_id, headers)
        if method == "POST":
            return self._link_dossier_evidence(dossier_id, headers, body)
        return ApiResponse.json(405, {"error": "method_not_allowed"})

    @staticmethod
    def _dossier_media_route(path: str) -> tuple[str, str] | None:
        prefix = "/api/v1/dossiers/"
        if not path.startswith(prefix):
            return None
        parts = path[len(prefix) :].strip("/").split("/")
        if len(parts) == 2 and parts[1] == "media-links":
            dossier_id = unquote(parts[0]).strip()
            return (dossier_id, "") if dossier_id else None
        if len(parts) == 3 and parts[1] == "media-links":
            dossier_id = unquote(parts[0]).strip()
            media_id = unquote(parts[2]).strip()
            if dossier_id and media_id and "/" not in dossier_id and "/" not in media_id:
                return dossier_id, media_id
        return None

    def _dossier_record(
        self, organization_id: str, dossier_id: str
    ) -> dict[str, object] | None:
        for record in self._science.records("dossiers"):
            if str(record.get("id", "")).strip() != dossier_id:
                continue
            record_org = str(record.get("organization_id", "")).strip()
            if record_org and record_org != organization_id:
                return None
            return record
        return None

    def _dossier_identity(self, headers: dict[str, str]):
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return None
        return identity

    def _allowed(
        self,
        identity,
        action: str,
        resource_type: str,
        resource_id: str,
        project_id: str,
        purpose: str,
    ) -> bool:
        return self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                resource_type,
                resource_id,
                identity.organization_id,
                project_id,
                purpose,
            )
        ).allowed

    def _dossier_context(
        self, dossier_id: str, headers: dict[str, str], action: str
    ):
        identity = self._dossier_identity(headers)
        if identity is None:
            return None, None, ""
        dossier = self._dossier_record(identity.organization_id, dossier_id)
        if dossier is None:
            return identity, None, ""
        project_id = str(dossier.get("project_id", "")).strip()
        purpose = headers.get("x-fieldora-purpose", "research")
        if not self._allowed(
            identity, action, "dossier", dossier_id, project_id, purpose
        ):
            return identity, None, project_id
        return identity, dossier, project_id

    def _dossier_evidence(
        self, dossier_id: str, headers: dict[str, str]
    ) -> ApiResponse:
        if self._media is None:
            return ApiResponse.json(404, {"error": "not_found"})
        identity, dossier, project_id = self._dossier_context(
            dossier_id, headers, "view"
        )
        if identity is None:
            return ApiResponse.json(401, {"error": "unauthorized"})
        if dossier is None:
            return ApiResponse.json(404, {"error": "not_found"})
        purpose = headers.get("x-fieldora-purpose", "research")
        items: list[dict[str, object]] = []
        for media_id in self._media.associations.linked_media_ids(
            identity.organization_id, "dossier", dossier_id
        ):
            record = self._media.record(media_id)
            if record is None or record.organization_id != identity.organization_id:
                continue
            if not self._allowed(
                identity, "view", "asset", media_id, project_id, purpose
            ):
                continue
            association = next(
                (
                    link
                    for link in self._media.associations.links(
                        media_id, identity.organization_id
                    )
                    if link.association_type == "dossier"
                    and link.target_id == dossier_id
                ),
                None,
            )
            items.append(
                {
                    "media_id": record.media_id,
                    "mime_type": record.mime_type,
                    "size_bytes": record.size_bytes,
                    "sha256": record.sha256,
                    "linked_by": "" if association is None else association.linked_by,
                    "linked_at_epoch": (
                        0 if association is None else association.linked_at_epoch
                    ),
                }
            )
        return ApiResponse.json(200, {"items": items, "count": len(items)})

    def _link_dossier_evidence(
        self, dossier_id: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if self._media is None:
            return ApiResponse.json(404, {"error": "not_found"})
        if len(body) > 16_384:
            return ApiResponse.json(413, {"error": "request_too_large"})
        identity, dossier, project_id = self._dossier_context(
            dossier_id, headers, "edit"
        )
        if identity is None:
            return ApiResponse.json(401, {"error": "unauthorized"})
        if dossier is None:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            data = json.loads(body)
            media_id = str(data["media_id"]).strip()
            if not media_id:
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        record = self._media.record(media_id)
        if record is None or record.organization_id != identity.organization_id:
            return ApiResponse.json(404, {"error": "not_found"})
        purpose = headers.get("x-fieldora-purpose", "research")
        relationship_id = f"dossier:{dossier_id}:{media_id}"
        if not self._allowed(
            identity, "view", "asset", media_id, project_id, purpose
        ) or not self._allowed(
            identity,
            "link",
            "media_association",
            relationship_id,
            project_id,
            purpose,
        ):
            return ApiResponse.json(403, {"error": "forbidden"})
        association = new_association(
            media_id=record.media_id,
            organization_id=identity.organization_id,
            association_type="dossier",
            target_id=dossier_id,
            purpose=purpose,
            linked_by=identity.identity_id,
        )
        self._media.associations.link(association)
        return ApiResponse.json(201, {"item": association.as_dict()})

    def _unlink_dossier_evidence(
        self, dossier_id: str, media_id: str, headers: dict[str, str]
    ) -> ApiResponse:
        if self._media is None:
            return ApiResponse.json(404, {"error": "not_found"})
        identity, dossier, project_id = self._dossier_context(
            dossier_id, headers, "edit"
        )
        if identity is None:
            return ApiResponse.json(401, {"error": "unauthorized"})
        if dossier is None:
            return ApiResponse.json(404, {"error": "not_found"})
        record = self._media.record(media_id)
        if record is None or record.organization_id != identity.organization_id:
            return ApiResponse.json(404, {"error": "not_found"})
        purpose = headers.get("x-fieldora-purpose", "research")
        relationship_id = f"dossier:{dossier_id}:{media_id}"
        if not self._allowed(
            identity,
            "unlink",
            "media_association",
            relationship_id,
            project_id,
            purpose,
        ):
            return ApiResponse.json(403, {"error": "forbidden"})
        self._media.associations.unlink(
            record.media_id,
            identity.organization_id,
            "dossier",
            dossier_id,
        )
        return ApiResponse(204, b"")
