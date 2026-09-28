"""Server-authoritative media-type normalization at the upload API boundary."""

from __future__ import annotations

import json

from natureai_next.domain.access_control import AccessRequest, Identity
from natureai_next.server.api import ApiResponse
from natureai_next.server.media_types import canonical_media_type


class CanonicalMediaTypeApiMixin:
    """Normalize untrusted/generic client MIME declarations before persistence."""

    def _begin_upload(
        self, headers: dict[str, str], body: bytes, identity: Identity
    ) -> ApiResponse:
        if self._media is None or len(body) > 16_384:
            return ApiResponse.json(400, {"error": "invalid_request"})
        try:
            data = json.loads(body)
            project_id = str(data["project_id"])
            decision = self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "upload",
                    "asset",
                    "",
                    identity.organization_id,
                    project_id,
                    headers.get("x-fieldora-purpose", "research"),
                )
            )
            if not decision.allowed:
                return ApiResponse.json(403, {"error": "forbidden"})
            filename = str(data["filename"])
            upload = self._media.begin_upload(
                identity.identity_id,
                identity.organization_id,
                project_id,
                filename,
                canonical_media_type(filename, str(data.get("mime_type", ""))),
                int(data["size_bytes"]),
                str(data["sha256"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        return ApiResponse.json(
            201, {"upload_id": upload.upload_id, "received_bytes": 0}
        )
