"""Governed destructive Dossier deletion routes.

Deletion is a separate lifecycle slice because it mutates several Science collections
atomically. Library media and whiteboard documents remain owned by their source modules.
"""

from __future__ import annotations

from urllib.parse import unquote, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.domain.science import ScienceRevisionConflict
from natureai_next.server.api import ApiResponse


class DossierDeleteApiMixin:
    """Delete one Dossier and only its Dossier-owned Science associations."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        dossier_id = self._dossier_delete_route(urlsplit(target).path)
        if dossier_id is None or method != "DELETE":
            return super().dispatch(method, target, headers, body)
        return self._delete_dossier(dossier_id, headers)

    @staticmethod
    def _dossier_delete_route(path: str) -> str | None:
        prefix = "/api/v1/dossiers/"
        if not path.startswith(prefix):
            return None
        parts = path[len(prefix) :].strip("/").split("/")
        if len(parts) != 1:
            return None
        dossier_id = unquote(parts[0]).strip()
        if not dossier_id or "/" in dossier_id:
            return None
        return dossier_id

    def _delete_dossier(
        self, dossier_id: str, headers: dict[str, str]
    ) -> ApiResponse:
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "unauthorized"})

        snapshot, revision = self._science.load_snapshot()
        dossiers = snapshot.get("dossiers", [])
        dossier = next(
            (
                record
                for record in dossiers
                if str(record.get("id", "")).strip() == dossier_id
                and str(record.get("organization_id", "")).strip()
                in {"", identity.organization_id}
            ),
            None,
        )
        if dossier is None:
            return ApiResponse.json(404, {"error": "not_found"})

        project_id = str(dossier.get("project_id", "")).strip()
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

        snapshot["dossiers"] = [
            record
            for record in dossiers
            if str(record.get("id", "")).strip() != dossier_id
        ]
        snapshot["dossier_whiteboards"] = [
            link
            for link in snapshot.get("dossier_whiteboards", [])
            if str(link.get("dossier_id", "")).strip() != dossier_id
        ]
        snapshot["dossier_links"] = [
            link
            for link in snapshot.get("dossier_links", [])
            if dossier_id
            not in {
                str(link.get("parent_dossier_id", "")).strip(),
                str(link.get("child_dossier_id", "")).strip(),
            }
        ]
        try:
            self._science.save_snapshot(snapshot, expected_revision=revision)
        except ScienceRevisionConflict:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse(204, b"")
