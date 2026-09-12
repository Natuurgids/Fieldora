"""Governed Dossier duplication routes.

Duplication is a separate lifecycle slice because it creates a new governed record while
preserving only Dossier-owned Science associations. Library media remains owned by the
Library module and is never copied or relinked implicitly.
"""

from __future__ import annotations

import json
import time
from copy import deepcopy
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.domain.science import ScienceRevisionConflict
from natureai_next.server.api import ApiResponse


class DossierDuplicateApiMixin:
    """Duplicate one Dossier without cloning Library-owned evidence."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        dossier_id = self._dossier_duplicate_route(urlsplit(target).path)
        if dossier_id is None:
            return super().dispatch(method, target, headers, body)
        if method != "POST":
            return ApiResponse.json(405, {"error": "method_not_allowed"})
        return self._duplicate_dossier(dossier_id, headers, body)

    @staticmethod
    def _dossier_duplicate_route(path: str) -> str | None:
        prefix = "/api/v1/dossiers/"
        if not path.startswith(prefix):
            return None
        parts = path[len(prefix) :].strip("/").split("/")
        if len(parts) != 2 or parts[1] != "duplicate":
            return None
        dossier_id = unquote(parts[0]).strip()
        if not dossier_id or "/" in dossier_id:
            return None
        return dossier_id

    @staticmethod
    def _duplicate_payload(body: bytes) -> dict[str, object] | None:
        if not body:
            return {}
        if len(body) > 16_384:
            return None
        try:
            payload = json.loads(body)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _duplicate_dossier(
        self, dossier_id: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})

        snapshot, revision = self._science.load_snapshot()
        source = next(
            (
                record
                for record in snapshot.get("dossiers", [])
                if str(record.get("id", "")).strip() == dossier_id
                and str(record.get("organization_id", "")).strip()
                in {"", identity.organization_id}
            ),
            None,
        )
        if source is None:
            return ApiResponse.json(404, {"error": "not_found"})

        project_id = str(source.get("project_id", "")).strip()
        purpose = headers.get("x-fieldora-purpose", "research")
        allowed = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "edit",
                "dossier",
                dossier_id,
                identity.organization_id,
                project_id,
                purpose,
            )
        ).allowed
        if not allowed:
            return ApiResponse.json(404, {"error": "not_found"})

        payload = self._duplicate_payload(body)
        if payload is None:
            return ApiResponse.json(400, {"error": "invalid_request"})

        duplicate = deepcopy(source)
        duplicate_id = str(uuid4())
        duplicate["id"] = duplicate_id
        duplicate["organization_id"] = identity.organization_id
        duplicate["source_dossier_id"] = dossier_id
        duplicate["owner_id"] = identity.identity_id
        duplicate["created_by"] = identity.identity_id
        duplicate["updated_by"] = identity.identity_id
        duplicate["reviewer_id"] = ""
        duplicate["review_status"] = "draft"
        duplicate["review_history"] = [
            {
                "action": "dossier_duplicated",
                "actor_id": identity.identity_id,
                "remark": f"Duplicated from {dossier_id}",
                "recorded_at_epoch": int(time.time()),
            }
        ]

        for key in ("name", "title"):
            if key in payload:
                value = str(payload[key]).strip()
                if not value:
                    return ApiResponse.json(400, {"error": "invalid_request"})
                duplicate[key] = value
            elif str(duplicate.get(key, "")).strip():
                duplicate[key] = f"{str(duplicate[key]).strip()} (copy)"

        snapshot.setdefault("dossiers", []).append(duplicate)
        source_whiteboards = tuple(snapshot.get("dossier_whiteboards", []))
        for link in source_whiteboards:
            if str(link.get("dossier_id", "")).strip() != dossier_id:
                continue
            copied_link = deepcopy(link)
            copied_link["dossier_id"] = duplicate_id
            snapshot.setdefault("dossier_whiteboards", []).append(copied_link)

        try:
            new_revision = self._science.save_snapshot(
                snapshot, expected_revision=revision
            )
        except ScienceRevisionConflict:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(
            201,
            {
                "item": duplicate,
                "revision": new_revision.database_revision,
            },
        )
