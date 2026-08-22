"""Fieldora Platform API extensions over the existing governed server boundary.

The base :class:`FieldoraApi` remains the authentication, quota, PBAC, and existing
science/media boundary. New platform namespaces first pass through that boundary; only
its authenticated 404 is replaced. This prevents a second security stack from forming.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from natureai_next.domain.access_control import AccessRequest, Identity
from natureai_next.server.api import ApiResponse, FieldoraApi
from natureai_next.server.operator_control import (
    PostgresOperatorRepository,
    ServiceState,
    SqliteOperatorRepository,
    operator_snapshot,
)
from natureai_next.server.scientific_collaboration import (
    PostgresCollaborationRepository,
    SqliteCollaborationRepository,
)
from natureai_next.server.tenant_governance import (
    PostgresTenantGovernance,
    SqliteTenantGovernance,
)


class PlatformFieldoraApi(FieldoraApi):
    """Add project-independent intake, expert review, and operator control."""

    _PLATFORM_PREFIXES = (
        "/api/v1/submissions",
        "/api/v1/review-cases",
        "/api/v1/operator",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        governance = self._governance
        if isinstance(governance, PostgresTenantGovernance):
            self._operator = PostgresOperatorRepository(governance._connect)
            self._collaboration = PostgresCollaborationRepository(governance._connect)
        elif isinstance(governance, SqliteTenantGovernance):
            parent = governance._database_path.parent
            self._operator = SqliteOperatorRepository(parent / "operator-control.sqlite3")
            self._collaboration = SqliteCollaborationRepository(
                parent / "scientific-collaboration.sqlite3"
            )
        else:
            data_root = self._fallback_data_root()
            self._operator = SqliteOperatorRepository(data_root / "operator-control.sqlite3")
            self._collaboration = SqliteCollaborationRepository(
                data_root / "scientific-collaboration.sqlite3"
            )

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        path = urlsplit(target).path
        if not path.startswith(self._PLATFORM_PREFIXES):
            return super().dispatch(method, target, headers, body)

        gate = super().dispatch(method, target, headers, body)
        if gate.status != 404:
            return gate

        _token, identity = self._identity(headers)
        if path.startswith("/api/v1/operator"):
            return self._operator_dispatch(method, target, headers, body, identity)
        if path.startswith("/api/v1/submissions"):
            return self._submission_dispatch(method, target, headers, body, identity)
        return self._review_dispatch(method, target, headers, body, identity)

    def _begin_upload(
        self, headers: dict[str, str], body: bytes, identity: Identity
    ) -> ApiResponse:
        """Begin upload to the organization Library; project context is optional."""
        if self._media is None or len(body) > 16_384:
            return ApiResponse.json(400, {"error": "invalid_request"})
        try:
            data = json.loads(body)
            project_id = str(data.get("project_id", "")).strip()
            if not self._allow(
                identity,
                headers,
                "upload",
                "asset",
                "",
                project_id,
                "research",
            ):
                return ApiResponse.json(403, {"error": "forbidden"})
            upload = self._media.begin_upload(
                identity.identity_id,
                identity.organization_id,
                project_id,
                str(data["filename"]),
                str(data.get("mime_type", "")),
                int(data["size_bytes"]),
                str(data["sha256"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        return ApiResponse.json(
            201,
            {
                "upload_id": upload.upload_id,
                "received_bytes": 0,
                "scope": "project" if project_id else "library",
            },
        )

    def _create_staged_submission(
        self, headers: dict[str, str], body: bytes, identity: Identity
    ) -> ApiResponse:
        """Create quarantine intake without inventing a synthetic project."""
        if self._staged_ingestion is None or len(body) > 16_384:
            return ApiResponse.json(400, {"error": "staged_ingestion_unavailable"})
        try:
            data = json.loads(body)
            project_id = str(data.get("project_id", "")).strip()
            purpose = str(
                data.get("purpose") or headers.get("x-fieldora-purpose", "research")
            ).strip()
            if not self._allow(
                identity, headers, "upload", "asset", "", project_id, purpose
            ):
                return ApiResponse.json(403, {"error": "forbidden"})
            contract_id = str(data.get("contract_id", "")).strip()
            if contract_id:
                if not project_id or self._access_repository is None:
                    return ApiResponse.json(
                        409, {"error": "contract_requires_project_scope"}
                    )
                contract = self._access_repository.contract(contract_id)
                if (
                    contract is None
                    or not contract.active_at(datetime.now(UTC).isoformat())
                    or contract.organization_id != identity.organization_id
                    or str(contract.terms.get("project_id", "")) != project_id
                ):
                    return ApiResponse.json(
                        409, {"error": "inactive_or_mismatched_contract"}
                    )
            submission = self._staged_ingestion.store.create_submission(
                subject_id=identity.identity_id,
                organization_id=identity.organization_id,
                project_id=project_id,
                contract_id=contract_id,
                purpose=purpose,
                publication_policy=str(data.get("publication_policy", "review")),
                expected_files=int(data["expected_files"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_submission"})
        return ApiResponse.json(
            201,
            {"submission": self._staged_submission_payload(submission)},
        )

    def _submission_dispatch(
        self,
        method: str,
        target: str,
        headers: dict[str, str],
        body: bytes,
        identity: Identity,
    ) -> ApiResponse:
        route = urlsplit(target)
        parts = [item for item in route.path.split("/") if item]
        if route.path == "/api/v1/submissions" and method == "POST":
            if not self._allow(
                identity, headers, "submit_evidence", "submission", "", "", "research"
            ):
                return ApiResponse.json(403, {"error": "forbidden"})
            try:
                data = self._json(body)
                item = self._collaboration.create_submission(
                    organization_id=identity.organization_id,
                    submitted_by=identity.identity_id,
                    source_type=str(data.get("source_type", "direct")),
                    source_reference=str(data.get("source_reference", "")),
                    project_id=str(data.get("project_id", "")),
                    collection_id=str(data.get("collection_id", "")),
                    license_id=str(data.get("license_id", "")),
                    consent_code=str(data.get("consent_code", "")),
                    purpose=str(data.get("purpose", "research")),
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_submission"})
            return ApiResponse.json(201, {"submission": item.as_dict()})
        if route.path == "/api/v1/submissions" and method == "GET":
            if not self._allow(
                identity, headers, "view_submission", "submission", "", "", "research"
            ):
                return ApiResponse.json(403, {"error": "forbidden"})
            limit = self._query_limit(route.query)
            if limit is None:
                return ApiResponse.json(400, {"error": "invalid_limit"})
            items = [
                item.as_dict()
                for item in self._collaboration.submissions(
                    identity.organization_id, limit
                )
            ]
            return ApiResponse.json(200, {"items": items, "count": len(items)})
        if len(parts) == 4 and method == "GET":
            item = self._collaboration.submission(parts[-1])
            if item is None or item.organization_id != identity.organization_id:
                return ApiResponse.json(404, {"error": "not_found"})
            if not self._allow(
                identity,
                headers,
                "view_submission",
                "submission",
                item.submission_id,
                item.project_id,
                item.purpose,
            ):
                return ApiResponse.json(404, {"error": "not_found"})
            return ApiResponse.json(200, {"submission": item.as_dict()})
        return ApiResponse.json(404, {"error": "not_found"})

    def _review_dispatch(
        self,
        method: str,
        target: str,
        headers: dict[str, str],
        body: bytes,
        identity: Identity,
    ) -> ApiResponse:
        route = urlsplit(target)
        prefix = "/api/v1/review-cases"
        suffix = route.path.removeprefix(prefix).strip("/")
        parts = [] if not suffix else suffix.split("/")
        if not parts and method == "POST":
            try:
                data = self._json(body)
                project_id = str(data.get("project_id", "")).strip()
                if not self._allow(
                    identity,
                    headers,
                    "request_review",
                    "review_case",
                    "",
                    project_id,
                    "research",
                ):
                    return ApiResponse.json(403, {"error": "forbidden"})
                item = self._collaboration.create_review_case(
                    organization_id=identity.organization_id,
                    subject_type=str(data["subject_type"]),
                    subject_id=str(data["subject_id"]),
                    project_id=project_id,
                    domain=str(data["domain"]),
                    specialty=str(data.get("specialty", "")),
                    geography=str(data.get("geography", "")),
                    requested_by=identity.identity_id,
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_review_case"})
            return ApiResponse.json(201, {"review_case": item.as_dict()})
        if not parts and method == "GET":
            if not self._allow(
                identity, headers, "view_review", "review_case", "", "", "research"
            ):
                return ApiResponse.json(403, {"error": "forbidden"})
            limit = self._query_limit(route.query)
            if limit is None:
                return ApiResponse.json(400, {"error": "invalid_limit"})
            items = [
                item.as_dict()
                for item in self._collaboration.review_cases(
                    identity.organization_id, limit
                )
            ]
            return ApiResponse.json(200, {"items": items, "count": len(items)})
        if len(parts) == 1 and method == "GET":
            case = self._collaboration.review_case(parts[0])
            if not self._review_visible(case, identity, headers):
                return ApiResponse.json(404, {"error": "not_found"})
            return ApiResponse.json(
                200,
                {
                    "review_case": case.as_dict(),
                    "determinations": [
                        item.as_dict()
                        for item in self._collaboration.determinations(case.review_case_id)
                    ],
                },
            )
        if len(parts) == 2 and parts[1] == "determinations" and method == "POST":
            case = self._collaboration.review_case(parts[0])
            if case is None or case.organization_id != identity.organization_id:
                return ApiResponse.json(404, {"error": "not_found"})
            if not self._allow(
                identity,
                headers,
                "determine",
                "review_case",
                case.review_case_id,
                case.project_id,
                "research",
            ):
                return ApiResponse.json(403, {"error": "forbidden"})
            try:
                data = self._json(body)
                item = self._collaboration.add_determination(
                    review_case_id=case.review_case_id,
                    expert_id=identity.identity_id,
                    assertion=str(data["assertion"]),
                    confidence=float(data.get("confidence", 0)),
                    evidence_json=data.get("evidence", {}),
                    supersedes_id=str(data.get("supersedes_id", "")),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_determination"})
            return ApiResponse.json(201, {"determination": item.as_dict()})
        if len(parts) == 2 and parts[1] == "accept" and method == "POST":
            case = self._collaboration.review_case(parts[0])
            if case is None or case.organization_id != identity.organization_id:
                return ApiResponse.json(404, {"error": "not_found"})
            if not self._allow(
                identity,
                headers,
                "accept_determination",
                "review_case",
                case.review_case_id,
                case.project_id,
                "research",
            ):
                return ApiResponse.json(403, {"error": "forbidden"})
            try:
                determination_id = str(self._json(body)["determination_id"])
                updated = self._collaboration.accept_determination(
                    case.review_case_id, determination_id
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_determination"})
            return ApiResponse.json(200, {"review_case": updated.as_dict()})
        return ApiResponse.json(404, {"error": "not_found"})

    def _operator_dispatch(
        self,
        method: str,
        target: str,
        headers: dict[str, str],
        body: bytes,
        identity: Identity,
    ) -> ApiResponse:
        route = urlsplit(target)
        prefix = "/api/v1/operator"
        suffix = route.path.removeprefix(prefix).strip("/")
        parts = [] if not suffix else suffix.split("/")
        if parts == ["overview"] and method == "GET":
            if not self._allow_operator(identity, headers, "infrastructure.view", ""):
                return ApiResponse.json(403, {"error": "forbidden"})
            snapshot = operator_snapshot(
                self._operator,
                identity.organization_id,
                storage_paths=self._operator_storage_paths(),
            )
            snapshot["jobs"] = self._job_snapshot(identity.organization_id)
            snapshot["runtime"] = dict(self._runtime_profile)
            return ApiResponse.json(200, snapshot)
        if parts == ["services"] and method == "GET":
            if not self._allow_operator(identity, headers, "infrastructure.view", ""):
                return ApiResponse.json(403, {"error": "forbidden"})
            items = [
                item.as_dict()
                for item in self._operator.services(identity.organization_id)
            ]
            return ApiResponse.json(200, {"items": items, "count": len(items)})
        if parts == ["services"] and method == "POST":
            if not self._allow_operator(identity, headers, "service.enroll", ""):
                return ApiResponse.json(403, {"error": "forbidden"})
            try:
                data = self._json(body)
                item = self._operator.enroll(
                    organization_id=identity.organization_id,
                    name=str(data["name"]),
                    service_type=str(data["service_type"]),
                    node_name=str(data["node_name"]),
                    software_version=str(data.get("software_version", "")),
                    configuration_sha256=str(data.get("configuration_sha256", "")),
                    certificate_serial=str(data["certificate_serial"]),
                    certificate_not_after_epoch=int(data["certificate_not_after_epoch"]),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_service"})
            return ApiResponse.json(201, {"service": item.as_dict()})
        if len(parts) == 3 and parts[0] == "services" and method == "POST":
            service_id, operation = parts[1], parts[2]
            service = self._operator.service(service_id)
            if service is None or service.organization_id != identity.organization_id:
                return ApiResponse.json(404, {"error": "not_found"})
            if operation == "heartbeat":
                action = "service.heartbeat"
                if not self._allow_operator(identity, headers, action, service_id):
                    return ApiResponse.json(403, {"error": "forbidden"})
                try:
                    data = self._json(body)
                    updated = self._operator.heartbeat(
                        service_id,
                        software_version=str(data.get("software_version", "")),
                        configuration_sha256=str(
                            data.get("configuration_sha256", "")
                        ),
                        certificate_serial=str(data.get("certificate_serial", "")),
                        certificate_not_after_epoch=(
                            int(data["certificate_not_after_epoch"])
                            if "certificate_not_after_epoch" in data
                            else None
                        ),
                    )
                except (PermissionError, TypeError, ValueError, json.JSONDecodeError):
                    return ApiResponse.json(409, {"error": "heartbeat_rejected"})
                return ApiResponse.json(200, {"service": updated.as_dict()})
            transitions = {
                "activate": ServiceState.ACTIVE,
                "drain": ServiceState.DRAINING,
                "stop": ServiceState.STOPPED,
                "revoke": ServiceState.REVOKED,
            }
            target_state = transitions.get(operation)
            if target_state is None:
                return ApiResponse.json(404, {"error": "not_found"})
            if not self._allow_operator(
                identity, headers, f"service.{operation}", service_id
            ):
                return ApiResponse.json(403, {"error": "forbidden"})
            try:
                updated = self._operator.transition(service_id, target_state)
            except (KeyError, ValueError):
                return ApiResponse.json(409, {"error": "invalid_service_transition"})
            return ApiResponse.json(200, {"service": updated.as_dict()})
        return ApiResponse.json(404, {"error": "not_found"})

    def _review_visible(
        self, case: Any, identity: Identity, headers: dict[str, str]
    ) -> bool:
        return bool(
            case is not None
            and case.organization_id == identity.organization_id
            and self._allow(
                identity,
                headers,
                "view_review",
                "review_case",
                case.review_case_id,
                case.project_id,
                "research",
            )
        )

    def _allow_operator(
        self,
        identity: Identity,
        headers: dict[str, str],
        action: str,
        resource_id: str,
    ) -> bool:
        return self._allow(
            identity,
            headers,
            action,
            "infrastructure",
            resource_id,
            "",
            "administration",
        )

    def _allow(
        self,
        identity: Identity,
        headers: dict[str, str],
        action: str,
        resource_type: str,
        resource_id: str,
        project_id: str,
        default_purpose: str,
    ) -> bool:
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                resource_type,
                resource_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", default_purpose),
            )
        )
        return bool(decision.allowed)

    def _operator_storage_paths(self) -> tuple[Path, ...]:
        paths: list[Path] = []
        storage = getattr(self._media, "_storage_root", None)
        if isinstance(storage, Path):
            paths.append(storage)
        exports = getattr(self._exports, "_root", None)
        if isinstance(exports, Path) and exports not in paths:
            paths.append(exports)
        return tuple(paths)

    def _fallback_data_root(self) -> Path:
        storage = getattr(self._media, "_storage_root", None)
        if isinstance(storage, Path):
            return storage.parent / "subsystems"
        return Path.cwd() / ".fieldora-platform"

    def _job_snapshot(self, organization_id: str) -> dict[str, object]:
        database_path = getattr(self._jobs, "_database_path", None)
        if isinstance(database_path, Path) and database_path.is_file():
            connection = sqlite3.connect(database_path)
            try:
                rows = connection.execute(
                    "SELECT status,COUNT(*) FROM server_jobs WHERE organization_id=? "
                    "GROUP BY status ORDER BY status",
                    (organization_id,),
                ).fetchall()
                oldest = connection.execute(
                    "SELECT created_at_utc FROM server_jobs WHERE organization_id=? "
                    "AND status='queued' ORDER BY created_at_utc LIMIT 1",
                    (organization_id,),
                ).fetchone()
            finally:
                connection.close()
            return {
                "by_status": {str(status): int(count) for status, count in rows},
                "oldest_queued_at_utc": "" if oldest is None else str(oldest[0]),
            }
        connect = getattr(self._jobs, "_connect", None)
        if callable(connect):
            with connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT status,COUNT(*) FROM server_jobs WHERE organization_id=%s "
                        "GROUP BY status ORDER BY status",
                        (organization_id,),
                    )
                    rows = cursor.fetchall()
                    cursor.execute(
                        "SELECT created_at_utc FROM server_jobs WHERE organization_id=%s "
                        "AND status='queued' ORDER BY created_at_utc LIMIT 1",
                        (organization_id,),
                    )
                    oldest = cursor.fetchone()
            return {
                "by_status": {str(status): int(count) for status, count in rows},
                "oldest_queued_at_utc": "" if oldest is None else str(oldest[0]),
            }
        return {"by_status": {}, "oldest_queued_at_utc": ""}

    @staticmethod
    def _query_limit(query: str) -> int | None:
        try:
            return max(1, min(int(parse_qs(query).get("limit", ["100"])[0]), 500))
        except ValueError:
            return None

    @staticmethod
    def _json(body: bytes) -> dict[str, Any]:
        if len(body) > 64 * 1024:
            raise ValueError("request too large")
        value = json.loads(body or b"{}")
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value
