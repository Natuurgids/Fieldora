"""Governed API for the source-project owner used by sharing approvals."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse
from natureai_next.server.recipient_contract_api import RecipientContractFieldoraApi


class ProjectOwnerContractFieldoraApi(RecipientContractFieldoraApi):
    """Persist and disclose the owner who must attest project-governed sharing."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        if response.status != 404 or self._barriers is None:
            return response
        route = urlsplit(target)
        parts = [part for part in route.path.split("/") if part]
        if (
            len(parts) != 6
            or parts[:3] != ["api", "v1", "access-barriers"]
            or parts[3] != "projects"
            or parts[5] != "owner"
        ):
            return response
        project_id = parts[4]
        try:
            _token, identity = self._identity(headers)
        except Exception:
            return response
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "administer_contracts",
                "contract",
                f"project-owner:{project_id}",
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "administration"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(404, {"error": "not_found"})

        if method == "GET":
            owner = self._barriers.project_owner(project_id)
            return ApiResponse.json(
                200,
                {"project_id": project_id, "owner": None if owner is None else owner.__dict__},
            )
        if method == "POST":
            try:
                data = json.loads(body)
                owner_identity = str(data["owner_identity"]).strip()
                if not owner_identity or self._access_repository is None:
                    raise ValueError
                owner = self._access_repository.identity(owner_identity)
                if owner is None or not owner.enabled:
                    return ApiResponse.json(409, {"error": "invalid_project_owner"})
                record = self._barriers.assign_project_owner(
                    project_id,
                    owner_identity,
                    assigned_by=identity.identity_id,
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_project_owner"})
            return ApiResponse.json(
                200,
                {
                    "project_id": record.project_id,
                    "owner_identity": record.owner_identity,
                    "assigned_by": record.assigned_by,
                    "assigned_at_epoch": record.assigned_at_epoch,
                },
            )
        return response
