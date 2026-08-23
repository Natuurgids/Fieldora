"""Operator lifecycle and information-barrier gate for the managed Fieldora API."""

from __future__ import annotations

import json
import os
from urllib.parse import parse_qs, urlsplit

from natureai_next.domain.access_control import AccessRequest, Identity, IdentityKind
from natureai_next.server.access_contracts import (
    AccessTarget,
    AccessTargetKind,
    ContractDraft,
    ContractSubject,
    ContractSubjectKind,
    IntakeActorKind,
    IntakeContext,
    default_intake_contract,
    restrict_contract,
    sharing_amendment,
)
from natureai_next.server.api import ApiResponse
from natureai_next.server.facility_platform_api import CompletePlatformFieldoraApi
from natureai_next.server.operator_control import ServiceState
from natureai_next.server.required_access_barriers import RequiredAccessBarrierRepository


class RuntimeGovernedFieldoraApi(CompletePlatformFieldoraApi):
    """Keep services warm while enforcing lifecycle, PBAC, and evidence contracts."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._barriers = (
            None
            if self._access_repository is None
            else RequiredAccessBarrierRepository(self._access_repository._factory)
        )

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        path = route.path
        service_id = os.environ.get("FIELDORA_SERVICE_ID", "").strip()
        if service_id:
            record = self._operator.service(service_id)
            state = ServiceState.REVOKED if record is None else ServiceState(record.state)
            if path in {"/api/v1/health/live", "/api/v1/status"}:
                return super().dispatch(method, target, headers, body)
            if path == "/api/v1/health/ready" and state is not ServiceState.ACTIVE:
                return ApiResponse.json(
                    503,
                    {
                        "ready": False,
                        "service_id": service_id,
                        "service_state": state.value,
                        "detail": "service is not active",
                    },
                )
            if path.startswith("/api/v1/operator"):
                return super().dispatch(method, target, headers, body)
            if state is not ServiceState.ACTIVE:
                return ApiResponse.json(
                    503,
                    {
                        "error": "service_unavailable",
                        "service_id": service_id,
                        "service_state": state.value,
                    },
                )

        preflight = self._intake_preflight(method, path, headers, body)
        if preflight is not None:
            return preflight

        upload = None
        if (
            method == "PUT"
            and path.startswith("/api/v1/uploads/")
            and self._media is not None
        ):
            upload = self._media.upload(path.removeprefix("/api/v1/uploads/"))

        response = super().dispatch(method, target, headers, body)

        if path.startswith("/api/v1/access-barriers") and response.status == 404:
            _token, identity = self._identity(headers)
            return self._barrier_dispatch(method, target, headers, body, identity)

        if self._barriers is None:
            return response

        if upload is not None and response.status == 201:
            self._contract_completed_upload(upload, response, headers)

        if method == "GET" and path == "/api/v1/media" and response.status == 200:
            return self._filter_media_list(response, headers)
        if (
            method in {"GET", "HEAD"}
            and path.startswith("/api/v1/media/")
            and response.status in {200, 206}
        ):
            return self._filter_media_object(path, response, headers)
        if method == "GET" and path == "/api/v1/search" and response.status == 200:
            return self._filter_search(response, headers)
        return response

    def _intake_preflight(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
    ) -> ApiResponse | None:
        if method != "POST" or path not in {
            "/api/v1/uploads",
            "/api/v1/staged-submissions",
        }:
            return None
        try:
            _token, identity = self._identity(headers)
            data = json.loads(body)
            project_id = str(data.get("project_id", "")).strip()
            contract_id = str(data.get("contract_id", "")).strip()
        except Exception:
            return None
        memberships = self._project_memberships(identity.identity_id)
        if (
            identity.kind is IdentityKind.USER
            and memberships
            and not project_id
            and not contract_id
            and not self._is_platform_admin(identity)
        ):
            return ApiResponse.json(
                409,
                {
                    "error": "project_required_for_project_member",
                    "detail": "select one of the projects governing this intake",
                },
            )
        if (
            project_id
            and memberships
            and project_id not in memberships
            and not self._is_platform_admin(identity)
        ):
            return ApiResponse.json(403, {"error": "project_membership_required"})
        return None

    def _contract_completed_upload(
        self, upload, response: ApiResponse, headers: dict[str, str]
    ) -> None:
        if self._barriers is None:
            return
        try:
            media_id = str(json.loads(response.body)["media_id"])
            subject = ContractSubject(ContractSubjectKind.ASSET, media_id)
            # Mark first. If any subsequent derivation/persistence step fails, newly
            # governed evidence remains preserved but undisclosed rather than falling
            # through to the legacy PBAC-only compatibility behavior.
            self._barriers.require_contract(subject, reason="direct_governed_intake")
            if self._barriers.current(subject) is not None:
                return
            _token, identity = self._identity(headers)
            draft = self._default_contract_for_upload(identity, upload.project_id)
            draft = ContractDraft(
                draft.targets,
                draft.inherited_contract_id,
                draft.requires_project_owner_approval,
                draft.required_owner_signatures,
                source_project_id=draft.source_project_id,
                subject=subject,
            )
            if draft.inherited_contract_id and not draft.targets:
                targets = self._legacy_contract_targets(draft.inherited_contract_id)
                draft = ContractDraft(
                    targets,
                    draft.inherited_contract_id,
                    False,
                    0,
                    source_project_id=draft.source_project_id,
                    subject=subject,
                )
            self._barriers.create(draft, requested_by=identity.identity_id)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            # The media object is intentionally left contract-required. Operators can
            # inspect/remediate it without making the evidence visible prematurely.
            return

    def _default_contract_for_upload(self, identity: Identity, project_id: str) -> ContractDraft:
        memberships = self._project_memberships(identity.identity_id)
        existing = identity.attributes.get("contract_id", "").strip()
        if existing:
            kind = IntakeActorKind.CONTRACTED_CLIENT
        elif identity.kind is IdentityKind.SERVICE:
            kind = (
                IntakeActorKind.GLOBAL_SERVICE
                if identity.attributes.get("service_scope") == "global"
                else IntakeActorKind.ORGANIZATION_SERVICE
            )
        elif self._is_platform_admin(identity):
            kind = IntakeActorKind.ADMIN
        else:
            kind = IntakeActorKind.USER
        return default_intake_contract(
            IntakeContext(
                kind,
                identity.identity_id,
                organization_id=identity.organization_id,
                selected_project_id=project_id,
                project_memberships=memberships,
                existing_contract_id=existing,
            )
        )

    def _legacy_contract_targets(self, contract_id: str) -> tuple[AccessTarget, ...]:
        if self._access_repository is None:
            raise ValueError("contract repository unavailable")
        contract = self._access_repository.contract(contract_id)
        if contract is None or contract.status != "active":
            raise ValueError("inherited contract is not active")
        project_id = str(contract.terms.get("project_id", "")).strip()
        if project_id:
            return (
                AccessTarget(
                    AccessTargetKind.ORGANIZATION_PROJECT,
                    organization_id=contract.organization_id,
                    project_id=project_id,
                ),
            )
        return (
            AccessTarget(
                AccessTargetKind.ORGANIZATION,
                organization_id=contract.organization_id,
            ),
        )

    def _filter_media_list(
        self, response: ApiResponse, headers: dict[str, str]
    ) -> ApiResponse:
        _token, identity = self._identity(headers)
        memberships = self._project_memberships(identity.identity_id)
        payload = json.loads(response.body)
        items = [
            item
            for item in payload.get("items", [])
            if self._barriers.allows_asset(
                str(item["media_id"]),
                organization_id=identity.organization_id,
                project_ids=memberships,
            )
        ]
        return ApiResponse.json(200, {"items": items, "count": len(items)})

    def _filter_media_object(
        self, path: str, response: ApiResponse, headers: dict[str, str]
    ) -> ApiResponse:
        media_id = path.removeprefix("/api/v1/media/")
        _token, identity = self._identity(headers)
        if not self._barriers.allows_asset(
            media_id,
            organization_id=identity.organization_id,
            project_ids=self._project_memberships(identity.identity_id),
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        return response

    def _filter_search(
        self, response: ApiResponse, headers: dict[str, str]
    ) -> ApiResponse:
        _token, identity = self._identity(headers)
        memberships = self._project_memberships(identity.identity_id)
        payload = json.loads(response.body)
        items = []
        for item in payload.get("items", []):
            resource_type = str(item.get("resource_type", ""))
            resource_id = str(item.get("resource_id", ""))
            if resource_type == "asset" and not self._barriers.allows_asset(
                resource_id,
                organization_id=identity.organization_id,
                project_ids=memberships,
            ):
                continue
            if resource_type == "collection" and not self._barriers.allows(
                ContractSubject(ContractSubjectKind.COLLECTION, resource_id),
                organization_id=identity.organization_id,
                project_ids=memberships,
            ):
                continue
            items.append(item)
        return ApiResponse.json(200, {"items": items, "count": len(items)})

    def _barrier_dispatch(
        self,
        method: str,
        target: str,
        headers: dict[str, str],
        body: bytes,
        identity: Identity,
    ) -> ApiResponse:
        if self._barriers is None:
            return ApiResponse.json(503, {"error": "access_contracts_unavailable"})
        route = urlsplit(target)
        prefix = "/api/v1/access-barriers"
        suffix = route.path.removeprefix(prefix).strip("/")
        parts = [] if not suffix else suffix.split("/")

        if not parts and method == "GET":
            query = parse_qs(route.query)
            try:
                subject = ContractSubject(
                    ContractSubjectKind(query["subject_kind"][0]),
                    query["subject_id"][0],
                )
            except (KeyError, ValueError):
                return ApiResponse.json(400, {"error": "invalid_contract_subject"})
            current = self._barriers.current(subject)
            if current is None:
                return ApiResponse.json(200, {"contract": None})
            if not self._contract_allowed(identity, headers, "administer_contracts", current):
                return ApiResponse.json(404, {"error": "not_found"})
            return ApiResponse.json(
                200,
                {
                    "contract": current.as_dict(),
                    "signatures": [
                        item.as_dict()
                        for item in self._barriers.signatures(current.contract_id)
                    ],
                },
            )

        if not parts and method == "POST":
            try:
                data = json.loads(body)
                subject = ContractSubject(
                    ContractSubjectKind(str(data["subject_kind"])),
                    str(data["subject_id"]),
                )
                mode = str(data.get("mode", "create"))
                targets = self._targets(data.get("targets", []))
                current = self._barriers.current(subject)
                if mode == "restrict":
                    if current is None:
                        raise ValueError("no active contract to restrict")
                    if not self._contract_allowed(
                        identity, headers, "administer_contracts", current
                    ):
                        return ApiResponse.json(403, {"error": "forbidden"})
                    draft = restrict_contract(
                        ContractDraft(
                            current.targets,
                            "",
                            False,
                            0,
                            source_project_id=current.source_project_id,
                            subject=subject,
                        ),
                        subject=subject,
                        replacement_targets=targets,
                        administrator=True,
                    )
                elif mode == "share":
                    if current is None:
                        raise ValueError("no active contract to amend")
                    if current.source_project_id:
                        if not self._resource_edit_allowed(
                            identity, headers, subject, current.source_project_id
                        ):
                            return ApiResponse.json(403, {"error": "forbidden"})
                        admin_batch = False
                    else:
                        if not self._contract_allowed(
                            identity, headers, "administer_contracts", current
                        ):
                            return ApiResponse.json(403, {"error": "forbidden"})
                        admin_batch = True
                    draft = sharing_amendment(
                        ContractDraft(
                            current.targets,
                            "",
                            False,
                            0,
                            source_project_id=current.source_project_id,
                            subject=subject,
                        ),
                        requested_targets=targets,
                        administrator_batch=admin_batch,
                    )
                elif mode == "create":
                    project_id = str(data.get("source_project_id", "")).strip()
                    probe = ContractDraft(
                        targets,
                        "",
                        False,
                        0,
                        source_project_id=project_id,
                        subject=subject,
                    )
                    if not self._contract_allowed(
                        identity, headers, "administer_contracts", probe
                    ):
                        return ApiResponse.json(403, {"error": "forbidden"})
                    draft = probe
                else:
                    raise ValueError("invalid contract mode")
                item = self._barriers.create(
                    draft,
                    requested_by=identity.identity_id,
                    replaces_contract_id="" if current is None else current.contract_id,
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_access_contract"})
            return ApiResponse.json(201, {"contract": item.as_dict()})

        if len(parts) == 2 and parts[1] == "sign" and method == "POST":
            contract = self._barriers.contract(parts[0])
            if contract is None:
                return ApiResponse.json(404, {"error": "not_found"})
            if not self._contract_allowed(
                identity, headers, "approve_contracts", contract
            ):
                return ApiResponse.json(404, {"error": "not_found"})
            try:
                signature_id = str(json.loads(body)["signature_id"])
                updated = self._barriers.sign(
                    contract.contract_id,
                    owner_identity=identity.identity_id,
                    signature_id=signature_id,
                )
            except (KeyError, TypeError, ValueError, PermissionError, json.JSONDecodeError):
                return ApiResponse.json(409, {"error": "signature_conflict"})
            return ApiResponse.json(
                200,
                {
                    "contract": updated.as_dict(),
                    "signatures": [
                        item.as_dict()
                        for item in self._barriers.signatures(updated.contract_id)
                    ],
                },
            )

        if len(parts) == 4 and parts[0] == "collections" and parts[2] == "assets":
            collection_id, asset_id = parts[1], parts[3]
            probe = ContractDraft(
                (AccessTarget(AccessTargetKind.ALL),),
                "",
                False,
                0,
                subject=ContractSubject(ContractSubjectKind.COLLECTION, collection_id),
            )
            if not self._contract_allowed(
                identity, headers, "administer_contracts", probe
            ):
                return ApiResponse.json(403, {"error": "forbidden"})
            if method == "POST":
                self._barriers.link_collection_asset(collection_id, asset_id)
                return ApiResponse.json(200, {"linked": True})
            if method == "DELETE":
                self._barriers.unlink_collection_asset(collection_id, asset_id)
                return ApiResponse(204, b"")

        return ApiResponse.json(404, {"error": "not_found"})

    def _contract_allowed(
        self,
        identity: Identity,
        headers: dict[str, str],
        action: str,
        contract,
    ) -> bool:
        project_id = str(getattr(contract, "source_project_id", ""))
        contract_id = str(getattr(contract, "contract_id", ""))
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                "contract",
                contract_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "administration"),
            )
        )
        return decision.allowed

    def _resource_edit_allowed(
        self,
        identity: Identity,
        headers: dict[str, str],
        subject: ContractSubject,
        project_id: str,
    ) -> bool:
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                "edit",
                subject.kind.value,
                subject.subject_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        return decision.allowed

    def _project_memberships(self, identity_id: str) -> tuple[str, ...]:
        if self._access_repository is None:
            return ()
        connection = self._access_repository._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                "SELECT DISTINCT project_id FROM access_role_assignments "
                "WHERE subject_id=? AND project_id<>'' ORDER BY project_id",
                (identity_id,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(str(row[0]) for row in rows)

    def _is_platform_admin(self, identity: Identity) -> bool:
        return identity.attributes.get("platform_admin") == "true"

    @staticmethod
    def _targets(raw) -> tuple[AccessTarget, ...]:
        if not isinstance(raw, list) or not raw:
            raise ValueError("contract targets are required")
        values = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("contract target must be an object")
            values.append(
                AccessTarget(
                    AccessTargetKind(str(item["kind"])),
                    organization_id=str(item.get("organization_id", "")),
                    project_id=str(item.get("project_id", "")),
                )
            )
        return tuple(values)
