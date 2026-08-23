"""Governed ownership APIs and source-project sharing precedence."""

from __future__ import annotations

import json
from dataclasses import asdict
from urllib.parse import urlsplit

from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.access_contracts import ContractSubject, ContractSubjectKind
from natureai_next.server.api import ApiResponse
from natureai_next.server.contract_web_compatibility import patch_contract_web_response
from natureai_next.server.recipient_contract_api import RecipientContractFieldoraApi


class ProjectOwnerContractFieldoraApi(RecipientContractFieldoraApi):
    """Project owners may share only inside the evidence owner's contract ceiling."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        path = route.path

        if method == "POST" and path == "/api/v1/access-barriers":
            blocked = self._sharing_ceiling_preflight(body)
            if blocked is not None:
                return blocked

        response = patch_contract_web_response(
            target, super().dispatch(method, target, headers, body)
        )
        if response.status != 404 or self._barriers is None:
            return response

        parts = [part for part in path.split("/") if part]
        project_response = self._project_owner_route(method, parts, headers, body)
        if project_response is not None:
            return project_response
        evidence_response = self._evidence_owner_route(method, parts, headers, body)
        return response if evidence_response is None else evidence_response

    def _sharing_ceiling_preflight(self, body: bytes) -> ApiResponse | None:
        if self._barriers is None:
            return None
        try:
            data = json.loads(body)
            if str(data.get("mode", "")) != "share":
                return None
            subject = ContractSubject(
                ContractSubjectKind(str(data["subject_kind"])),
                str(data["subject_id"]),
            )
            current = self._barriers.current(subject)
            if current is None or not current.source_project_id:
                return None
            targets = self._targets(data.get("targets", []))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        if self._barriers.project_share_allowed_by_evidence_owner(subject, targets):
            return None
        return ApiResponse.json(
            409,
            {
                "error": "evidence_owner_contract_blocks_sharing",
                "detail": (
                    "the source project owner may share only within the evidence "
                    "owner's governing contract"
                ),
            },
        )

    def _project_owner_route(
        self,
        method: str,
        parts: list[str],
        headers: dict[str, str],
        body: bytes,
    ) -> ApiResponse | None:
        if (
            len(parts) != 6
            or parts[:3] != ["api", "v1", "access-barriers"]
            or parts[3] != "projects"
            or parts[5] != "owner"
        ):
            return None
        project_id = parts[4]
        identity = self._governance_identity(
            headers, project_id, f"project-owner:{project_id}"
        )
        if identity is None:
            return ApiResponse.json(404, {"error": "not_found"})

        if method == "GET":
            owner = self._barriers.project_owner(project_id)
            return ApiResponse.json(
                200,
                {
                    "project_id": project_id,
                    "owner": None if owner is None else asdict(owner),
                },
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
            return ApiResponse.json(200, asdict(record))
        return ApiResponse.json(405, {"error": "method_not_allowed"})

    def _evidence_owner_route(
        self,
        method: str,
        parts: list[str],
        headers: dict[str, str],
        body: bytes,
    ) -> ApiResponse | None:
        if (
            len(parts) != 7
            or parts[:3] != ["api", "v1", "access-barriers"]
            or parts[3] != "evidence"
            or parts[6] != "owner-contract"
        ):
            return None
        try:
            subject = ContractSubject(ContractSubjectKind(parts[4]), parts[5])
        except ValueError:
            return ApiResponse.json(400, {"error": "invalid_contract_subject"})
        identity = self._governance_identity(
            headers,
            "",
            f"evidence-owner:{subject.kind.value}:{subject.subject_id}",
        )
        if identity is None:
            return ApiResponse.json(404, {"error": "not_found"})

        if method == "GET":
            contract = self._barriers.evidence_owner_contract(subject)
            return ApiResponse.json(
                200,
                {
                    "subject_kind": subject.kind.value,
                    "subject_id": subject.subject_id,
                    "owner_contract": (
                        None if contract is None else _owner_contract_dict(contract)
                    ),
                },
            )
        if method == "POST":
            try:
                data = json.loads(body)
                owner_identity = str(data["owner_identity"]).strip()
                targets = self._targets(data.get("targets", []))
                if not owner_identity or self._access_repository is None:
                    raise ValueError
                owner = self._access_repository.identity(owner_identity)
                if owner is None or not owner.enabled:
                    return ApiResponse.json(409, {"error": "invalid_evidence_owner"})
                record = self._barriers.set_evidence_owner_contract(
                    subject,
                    owner_identity,
                    targets,
                    assigned_by=identity.identity_id,
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_evidence_owner_contract"})
            return ApiResponse.json(200, _owner_contract_dict(record))
        return ApiResponse.json(405, {"error": "method_not_allowed"})

    def _governance_identity(
        self,
        headers: dict[str, str],
        project_id: str,
        resource_id: str,
    ):
        try:
            _token, identity = self._identity(headers)
        except Exception:
            return None
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "administer_contracts",
                "contract",
                resource_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "administration"),
            )
        )
        return identity if decision.allowed else None


def _owner_contract_dict(contract) -> dict[str, object]:
    return {
        "subject_kind": contract.subject_kind,
        "subject_id": contract.subject_id,
        "owner_identity": contract.owner_identity,
        "targets": [
            {
                "kind": target.kind.value,
                "organization_id": target.organization_id,
                "project_id": target.project_id,
            }
            for target in contract.targets
        ],
        "assigned_by": contract.assigned_by,
        "assigned_at_epoch": contract.assigned_at_epoch,
    }
