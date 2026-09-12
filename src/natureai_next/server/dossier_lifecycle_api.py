"""Governed Dossier edit and review lifecycle routes.

The Science projection remains the authoritative persistence boundary. This mixin
adds only revisioned record mutations that the projection already supports;
destructive deletion and dossier composition remain separate parity slices.
"""

from __future__ import annotations

import json
import time
from urllib.parse import unquote, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest, IdentityKind
from natureai_next.server.api import ApiResponse


class DossierLifecycleApiMixin:
    """Expose fail-closed Dossier edit and review transitions."""

    _EDITABLE_FIELDS = frozenset(
        {
            "name",
            "title",
            "description",
            "notes",
            "dossier_type",
            "project_id",
            "parent_dossier_id",
        }
    )
    _DOSSIER_TYPES = frozenset({"dossier", "master"})

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        parsed = self._dossier_lifecycle_route(route.path)
        if parsed is None:
            return super().dispatch(method, target, headers, body)
        dossier_id, action = parsed
        if action == "edit" and method == "PATCH":
            return self._edit_dossier(dossier_id, headers, body)
        if action == "reassign-owner" and method == "POST":
            return self._reassign_dossier_owner(dossier_id, headers, body)
        if action == "defer" and method == "POST":
            return self._defer_dossier_review(dossier_id, headers, body)
        if action == "remark" and method == "POST":
            return self._remark_dossier_review(dossier_id, headers, body)
        if action == "return" and method == "POST":
            return self._return_dossier_review(dossier_id, headers, body)
        return ApiResponse.json(405, {"error": "method_not_allowed"})

    @staticmethod
    def _dossier_lifecycle_route(path: str) -> tuple[str, str] | None:
        prefix = "/api/v1/dossiers/"
        if not path.startswith(prefix):
            return None
        parts = path[len(prefix) :].strip("/").split("/")
        if len(parts) == 1:
            dossier_id = unquote(parts[0]).strip()
            if dossier_id and "/" not in dossier_id:
                return dossier_id, "edit"
            return None
        if len(parts) == 3 and parts[1] == "owner" and parts[2] == "reassign":
            dossier_id = unquote(parts[0]).strip()
            if dossier_id and "/" not in dossier_id:
                return dossier_id, "reassign-owner"
            return None
        if len(parts) == 3 and parts[1] == "review" and parts[2] in {
            "defer",
            "remark",
            "return",
        }:
            dossier_id = unquote(parts[0]).strip()
            if dossier_id and "/" not in dossier_id:
                return dossier_id, parts[2]
        return None

    def _lifecycle_identity(self, headers: dict[str, str]):
        try:
            _token, identity = self._identity(headers)
        except AuthenticationFailed:
            return None
        return identity

    def _lifecycle_record(
        self, organization_id: str, dossier_id: str
    ) -> dict[str, object] | None:
        for record in self._science.records("dossiers"):
            if str(record.get("id", "")).strip() != dossier_id:
                continue
            record_org = str(record.get("organization_id", "")).strip()
            if record_org and record_org != organization_id:
                return None
            return dict(record)
        return None

    def _lifecycle_allowed(
        self,
        identity,
        action: str,
        dossier_id: str,
        project_id: str,
        purpose: str,
    ) -> bool:
        return self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                "dossier",
                dossier_id,
                identity.organization_id,
                project_id,
                purpose,
            )
        ).allowed

    def _editable_context(
        self, dossier_id: str, headers: dict[str, str]
    ) -> tuple[object | None, dict[str, object] | None, str]:
        identity = self._lifecycle_identity(headers)
        if identity is None:
            return None, None, ""
        dossier = self._lifecycle_record(identity.organization_id, dossier_id)
        if dossier is None:
            return identity, None, ""
        project_id = str(dossier.get("project_id", "")).strip()
        purpose = headers.get("x-fieldora-purpose", "research")
        if not self._lifecycle_allowed(
            identity, "edit", dossier_id, project_id, purpose
        ):
            return identity, None, project_id
        return identity, dossier, project_id

    def _administrator_context(
        self, dossier_id: str, headers: dict[str, str]
    ) -> tuple[object | None, dict[str, object] | None, str]:
        identity = self._lifecycle_identity(headers)
        if identity is None:
            return None, None, ""
        dossier = self._lifecycle_record(identity.organization_id, dossier_id)
        if dossier is None:
            return identity, None, ""
        project_id = str(dossier.get("project_id", "")).strip()
        purpose = headers.get("x-fieldora-purpose", "research")
        if not self._lifecycle_allowed(
            identity, "reassign_owner", dossier_id, project_id, purpose
        ):
            return identity, None, project_id
        return identity, dossier, project_id

    def _eligible_user_identity(self, organization_id: str, identity_id: str) -> bool:
        repository = getattr(self, "_access_repository", None)
        if repository is None:
            return False
        target = repository.identity(identity_id)
        return bool(
            target is not None
            and target.kind is IdentityKind.USER
            and target.organization_id == organization_id
            and target.enabled
        )

    def _eligible_project(
        self, identity, project_id: str, purpose: str
    ) -> bool:
        if not project_id:
            return True
        management = getattr(self, "_project_management", None)
        if management is not None:
            exists = any(
                project.project_id == project_id
                for project in management.projects(identity.organization_id)
            )
        else:
            exists = any(
                str(project.get("id", "")).strip() == project_id
                and str(project.get("organization_id", "")).strip()
                in {"", identity.organization_id}
                for project in self._science.records("projects")
            )
        if not exists:
            return False
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

    @staticmethod
    def _payload(body: bytes) -> dict[str, object] | None:
        if len(body) > 16_384:
            return None
        try:
            payload = json.loads(body)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _expected_revision(headers: dict[str, str]) -> int | None:
        value = headers.get("if-match")
        if value is None or not value.strip():
            return None
        return int(value)

    def _save_dossier(
        self,
        dossier: dict[str, object],
        headers: dict[str, str],
    ) -> ApiResponse:
        try:
            expected = self._expected_revision(headers)
        except ValueError:
            return ApiResponse.json(400, {"error": "invalid_revision"})
        try:
            revision = self._science.put("dossiers", dossier, expected)
        except ValueError:
            return ApiResponse.json(409, {"error": "revision_conflict"})
        return ApiResponse.json(200, {"item": dossier, "revision": revision})

    @staticmethod
    def _append_review_history(
        dossier: dict[str, object],
        *,
        actor_id: str,
        action: str,
        remark: str = "",
    ) -> None:
        history = [
            dict(item)
            for item in dossier.get("review_history", [])
            if isinstance(item, dict)
        ]
        history.append(
            {
                "action": action,
                "actor_id": actor_id,
                "remark": remark,
                "recorded_at_epoch": int(time.time()),
            }
        )
        dossier["review_history"] = history

    def _edit_dossier(
        self, dossier_id: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        identity, dossier, _project_id = self._editable_context(dossier_id, headers)
        if identity is None:
            return ApiResponse.json(401, {"error": "unauthorized"})
        if dossier is None:
            return ApiResponse.json(404, {"error": "not_found"})
        payload = self._payload(body)
        if payload is None:
            return ApiResponse.json(400, {"error": "invalid_request"})
        updates = {key: payload[key] for key in self._EDITABLE_FIELDS if key in payload}
        if not updates:
            return ApiResponse.json(400, {"error": "invalid_request"})
        for key in ("name", "title"):
            if key in updates and not str(updates[key]).strip():
                return ApiResponse.json(400, {"error": "invalid_request"})
        if (
            "dossier_type" in updates
            and str(updates["dossier_type"]).strip() not in self._DOSSIER_TYPES
        ):
            return ApiResponse.json(400, {"error": "invalid_dossier_type"})
        if "project_id" in updates:
            target_project_id = str(updates["project_id"]).strip()
            if not self._eligible_project(
                identity,
                target_project_id,
                headers.get("x-fieldora-purpose", "research"),
            ):
                return ApiResponse.json(404, {"error": "project_not_found"})
            updates["project_id"] = target_project_id
        for key, value in updates.items():
            dossier[key] = str(value).strip() if isinstance(value, str) else value
        dossier["updated_by"] = identity.identity_id
        return self._save_dossier(dossier, headers)

    def _reassign_dossier_owner(
        self, dossier_id: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        identity, dossier, _project_id = self._administrator_context(dossier_id, headers)
        if identity is None:
            return ApiResponse.json(401, {"error": "unauthorized"})
        if dossier is None:
            return ApiResponse.json(404, {"error": "not_found"})
        payload = self._payload(body)
        if payload is None:
            return ApiResponse.json(400, {"error": "invalid_request"})
        new_owner = str(payload.get("owner_id", "")).strip()
        if not new_owner:
            return ApiResponse.json(400, {"error": "owner_required"})
        if not self._eligible_user_identity(identity.organization_id, new_owner):
            return ApiResponse.json(404, {"error": "owner_not_found"})
        previous = str(dossier.get("owner_id", dossier.get("created_by", ""))).strip()
        dossier["owner_id"] = new_owner
        dossier["updated_by"] = identity.identity_id
        self._append_review_history(
            dossier,
            actor_id=identity.identity_id,
            action="owner_reassigned",
            remark=f"{previous} → {new_owner}",
        )
        return self._save_dossier(dossier, headers)

    def _defer_dossier_review(
        self, dossier_id: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        identity, dossier, _project_id = self._editable_context(dossier_id, headers)
        if identity is None:
            return ApiResponse.json(401, {"error": "unauthorized"})
        if dossier is None:
            return ApiResponse.json(404, {"error": "not_found"})
        payload = self._payload(body)
        if payload is None:
            return ApiResponse.json(400, {"error": "invalid_request"})
        reviewer_id = str(payload.get("reviewer_id", "")).strip()
        if not reviewer_id:
            return ApiResponse.json(400, {"error": "reviewer_required"})
        if (
            reviewer_id == identity.identity_id
            or not self._eligible_user_identity(identity.organization_id, reviewer_id)
        ):
            return ApiResponse.json(404, {"error": "reviewer_not_found"})
        dossier.setdefault("owner_id", identity.identity_id)
        dossier["reviewer_id"] = reviewer_id
        dossier["review_status"] = "in_review"
        remark = str(payload.get("remark", "")).strip()
        self._append_review_history(
            dossier,
            actor_id=identity.identity_id,
            action="deferred_for_review",
            remark=remark or f"Assigned to {reviewer_id}",
        )
        return self._save_dossier(dossier, headers)

    def _reviewer_context(
        self, dossier_id: str, headers: dict[str, str]
    ) -> tuple[object | None, dict[str, object] | None, str]:
        identity = self._lifecycle_identity(headers)
        if identity is None:
            return None, None, ""
        dossier = self._lifecycle_record(identity.organization_id, dossier_id)
        if dossier is None:
            return identity, None, ""
        project_id = str(dossier.get("project_id", "")).strip()
        purpose = headers.get("x-fieldora-purpose", "research")
        reviewer_id = str(dossier.get("reviewer_id", "")).strip()
        if reviewer_id != identity.identity_id:
            return identity, None, project_id
        if not (
            self._lifecycle_allowed(
                identity, "review", dossier_id, project_id, purpose
            )
            or self._lifecycle_allowed(
                identity, "edit", dossier_id, project_id, purpose
            )
        ):
            return identity, None, project_id
        return identity, dossier, project_id

    def _remark_dossier_review(
        self, dossier_id: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        identity, dossier, _project_id = self._reviewer_context(dossier_id, headers)
        if identity is None:
            return ApiResponse.json(401, {"error": "unauthorized"})
        if dossier is None:
            return ApiResponse.json(404, {"error": "not_found"})
        if str(dossier.get("review_status", "")) != "in_review":
            return ApiResponse.json(409, {"error": "dossier_not_in_review"})
        payload = self._payload(body)
        if payload is None:
            return ApiResponse.json(400, {"error": "invalid_request"})
        remark = str(payload.get("remark", "")).strip()
        if not remark:
            return ApiResponse.json(400, {"error": "remark_required"})
        self._append_review_history(
            dossier,
            actor_id=identity.identity_id,
            action="review_remark",
            remark=remark,
        )
        return self._save_dossier(dossier, headers)

    def _return_dossier_review(
        self, dossier_id: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        identity, dossier, _project_id = self._reviewer_context(dossier_id, headers)
        if identity is None:
            return ApiResponse.json(401, {"error": "unauthorized"})
        if dossier is None:
            return ApiResponse.json(404, {"error": "not_found"})
        if str(dossier.get("review_status", "")) != "in_review":
            return ApiResponse.json(409, {"error": "dossier_not_in_review"})
        payload = self._payload(body)
        if payload is None:
            return ApiResponse.json(400, {"error": "invalid_request"})
        remark = str(payload.get("remark", "")).strip()
        dossier["review_status"] = "returned"
        self._append_review_history(
            dossier,
            actor_id=identity.identity_id,
            action="returned_to_observer",
            remark=remark,
        )
        return self._save_dossier(dossier, headers)
