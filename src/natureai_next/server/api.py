"""Dependency-free versioned HTTP application with PBAC-filtered Science reads."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

from natureai_next import __version__
from natureai_next.application.access_control import (
    AccessAdministrationService,
    PolicyDecisionService,
)
from natureai_next.application.authentication import (
    AuthenticationFailed,
    AuthenticationService,
)
from natureai_next.application.device_authorization import (
    DeviceAuthorizationPending,
    DeviceAuthorizationService,
)
from natureai_next.application.oidc import OidcAuthenticationService
from natureai_next.application.platform_features import parity_payload, registry_payload
from natureai_next.domain.access_control import AccessRequest, Identity
from natureai_next.infrastructure.database.access_control import (
    SqliteAccessControlRepository,
)
from natureai_next.server.exports import GovernedExportStore
from natureai_next.server.help import help_catalogue, help_topic
from natureai_next.server.jobs import ServerJobRepository
from natureai_next.server.media import GovernedMediaStore
from natureai_next.server.readiness import ReadinessMonitor
from natureai_next.server.search import SearchProjection
from natureai_next.server.staged_ingestion import StagedIngestionService
from natureai_next.server.tenant_governance import TenantGovernance


@dataclass(frozen=True, slots=True)
class ApiResponse:
    status: int
    body: bytes
    content_type: str = "application/json; charset=utf-8"
    headers: tuple[tuple[str, str], ...] = ()

    @classmethod
    def json(cls, status: int, payload: object) -> ApiResponse:
        return cls(
            status,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(),
        )


class ScienceProjection(Protocol):
    def records(self, collection: str) -> tuple[dict, ...]: ...
    def put(
        self, collection: str, record: dict, expected_revision: int | None
    ) -> int: ...


class ScienceReadProjection:
    """Read-only projection; PostgreSQL/search adapters can replace this boundary."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def records(self, collection: str) -> tuple[dict, ...]:
        if not self._database_path.is_file():
            return ()
        connection = sqlite3.connect(self._database_path)
        try:
            rows = connection.execute(
                "SELECT payload_json FROM science_records "
                "WHERE collection_name=? ORDER BY updated_at_us,record_id",
                (collection,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(json.loads(str(row[0])) for row in rows)

    def put(self, collection: str, record: dict, expected_revision: int | None) -> int:
        record_id = str(record["id"])
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, isolation_level=None)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT record_revision FROM science_records "
                "WHERE collection_name=? AND record_id=?",
                (collection, record_id),
            ).fetchone()
            current = 0 if row is None else int(row[0])
            if expected_revision is not None and current != expected_revision:
                raise ValueError("revision_conflict")
            revision = current + 1
            connection.execute(
                "INSERT INTO science_records(collection_name,record_id,payload_json,"
                "record_revision,updated_at_us) VALUES(?,?,?,?,?) "
                "ON CONFLICT(collection_name,record_id) DO UPDATE SET "
                "payload_json=excluded.payload_json,record_revision=excluded.record_revision,"
                "updated_at_us=excluded.updated_at_us",
                (
                    collection, record_id,
                    json.dumps(record, ensure_ascii=False, sort_keys=True),
                    revision, int(time.time() * 1_000_000),
                ),
            )
            connection.commit()
            return revision
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()


class LoginRateLimiter:
    def __init__(self, attempts: int = 5, window_seconds: int = 300) -> None:
        self._attempts = attempts
        self._window = window_seconds
        self._events: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        events = [item for item in self._events.get(key, []) if now - item < self._window]
        if len(events) >= self._attempts:
            self._events[key] = events
            return False
        events.append(now)
        self._events[key] = events
        return True


class FieldoraApi:
    def __init__(
        self,
        authentication: AuthenticationService,
        decisions: PolicyDecisionService,
        science: ScienceProjection,
        web_root: Path,
        media: GovernedMediaStore | None = None,
        device_authorization: DeviceAuthorizationService | None = None,
        oidc: OidcAuthenticationService | None = None,
        audit_repository: SqliteAccessControlRepository | None = None,
        search: SearchProjection | None = None,
        jobs: ServerJobRepository | None = None,
        exports: GovernedExportStore | None = None,
        governance: TenantGovernance | None = None,
        readiness: ReadinessMonitor | None = None,
        staged_ingestion: StagedIngestionService | None = None,
        runtime_profile: dict[str, str] | None = None,
    ) -> None:
        self._authentication = authentication
        self._decisions = decisions
        self._science = science
        self._web_root = web_root
        self._media = media
        self._device_authorization = device_authorization
        self._oidc = oidc
        self._audit_repository = audit_repository
        self._access_repository = audit_repository
        self._search = search
        self._jobs = jobs
        self._exports = exports
        self._governance = governance
        self._readiness = readiness
        self._staged_ingestion = staged_ingestion
        self._runtime_profile = dict(runtime_profile or {})
        self._login_limiter = LoginRateLimiter()

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        if route.path == "/" and method == "GET":
            return ApiResponse(
                200, (self._web_root / "index.html").read_bytes(),
                "text/html; charset=utf-8",
            )
        if route.path == "/app.js" and method == "GET":
            return ApiResponse(
                200, (self._web_root / "app.js").read_bytes(),
                "text/javascript; charset=utf-8",
            )
        if route.path == "/api/v1/status" and method == "GET":
            return ApiResponse.json(
                200, {"product": "Fieldora", "version": __version__, "api": "v1"}
            )
        if route.path == "/api/v1/health/live" and method == "GET":
            return ApiResponse.json(200, {"live": True})
        if route.path == "/api/v1/health/ready" and method == "GET":
            if self._readiness is None:
                return ApiResponse.json(
                    200, {"ready": True, "mode": "standalone"}
                )
            snapshot = self._readiness.snapshot()
            return ApiResponse.json(
                200 if snapshot.ready else 503, snapshot.as_dict()
            )
        if route.path == "/api/v1/session" and method == "POST":
            return self._login(headers, body)
        if route.path == "/api/v1/device/code" and method == "POST":
            return self._begin_device(body)
        if route.path == "/api/v1/device/token" and method == "POST":
            return self._exchange_device(body)
        try:
            token, identity = self._identity(headers)
        except AuthenticationFailed as exc:
            return ApiResponse.json(401, {"error": "unauthorized", "detail": str(exc)})
        if self._governance is not None:
            quota = self._governance.consume(
                identity.organization_id, "api_requests"
            )
            if not quota.allowed:
                retry_after = max(1, quota.resets_at_epoch - int(time.time()))
                return ApiResponse(
                    429,
                    json.dumps(
                        {
                            "error": "tenant_quota_exceeded",
                            "metric": quota.metric,
                            "limit": quota.limit,
                            "used": quota.used,
                        },
                        separators=(",", ":"),
                    ).encode(),
                    "application/json; charset=utf-8",
                    headers=(("Retry-After", str(retry_after)),),
                )
        if route.path == "/api/v1/session" and method == "DELETE":
            self._authentication.logout(token)
            return ApiResponse(204, b"")
        if route.path == "/api/v1/me" and method == "GET":
            return ApiResponse.json(
                200,
                {
                    "identity_id": identity.identity_id,
                    "display_name": identity.display_name,
                    "kind": identity.kind.value,
                    "organization_id": identity.organization_id,
                },
            )
        if route.path == "/api/v1/platform/features" and method == "GET":
            return ApiResponse.json(200, registry_payload())
        if route.path == "/api/v1/platform/parity" and method == "GET":
            return ApiResponse.json(200, parity_payload())
        if route.path == "/api/v1/runtime" and method == "GET":
            ready = {"ready": True, "mode": "standalone"} if self._readiness is None else self._readiness.snapshot().as_dict()
            return ApiResponse.json(200, {"version": __version__, "backends": self._runtime_profile, "readiness": ready})
        if route.path == "/api/v1/help" and method == "GET":
            return ApiResponse.json(200, {"items": help_catalogue()})
        if route.path.startswith("/api/v1/help/") and method == "GET":
            topic = help_topic(route.path.removeprefix("/api/v1/help/"))
            return (
                ApiResponse.json(200, topic)
                if topic is not None
                else ApiResponse.json(404, {"error": "help_topic_not_found"})
            )
        if route.path == "/api/v1/audit" and method == "GET":
            return self._audit_response(route.query, headers, identity)
        if route.path == "/api/v1/admin/contracts" and method == "POST":
            return self._create_contract(headers, body, identity)
        if route.path == "/api/v1/admin/contracts" and method == "GET":
            return self._contracts_response(route.query, headers, identity)
        if route.path == "/api/v1/admin/contract-approvals" and method == "GET":
            return self._contract_approvals_response(route.query, headers, identity)
        if route.path == "/api/v1/admin/contract-expiry" and method == "GET":
            return self._contract_expiry_response(route.query, headers, identity)
        if (
            route.path.startswith("/api/v1/admin/contracts/")
            and route.path.endswith("/approve")
            and method == "POST"
        ):
            return self._approve_contract(
                route.path.removeprefix("/api/v1/admin/contracts/").removesuffix(
                    "/approve"
                ),
                headers, identity,
            )
        if (
            route.path.startswith("/api/v1/admin/contracts/")
            and route.path.endswith("/status")
            and method == "POST"
        ):
            return self._set_contract_status(
                route.path.removeprefix("/api/v1/admin/contracts/").removesuffix(
                    "/status"
                ),
                headers, body, identity,
            )
        if route.path.startswith("/api/v1/admin/contracts/") and method == "GET":
            return self._contract_response(
                route.path.removeprefix("/api/v1/admin/contracts/"),
                headers, identity,
            )
        if route.path == "/api/v1/search" and method == "GET":
            return self._search_response(route.query, headers, identity)
        if route.path == "/api/v1/media" and method == "GET":
            return self._media_list_response(route.query, headers, identity)
        if route.path == "/api/v1/jobs" and method == "POST":
            return self._submit_job(headers, body, identity)
        if route.path.startswith("/api/v1/jobs/") and method == "GET":
            return self._job_response(
                route.path.removeprefix("/api/v1/jobs/"), headers, identity
            )
        if route.path.startswith("/api/v1/exports/") and method in ("GET", "HEAD"):
            if route.path.endswith("/attestation") and method == "GET":
                return self._export_attestation(
                    route.path.removeprefix("/api/v1/exports/").removesuffix(
                        "/attestation"
                    ),
                    headers, identity,
                )
            return self._export_response(
                route.path.removeprefix("/api/v1/exports/"),
                method, headers, identity,
            )
        if route.path.startswith("/api/v1/exports/") and method == "DELETE":
            return self._revoke_export(
                route.path.removeprefix("/api/v1/exports/"), headers, identity
            )
        if route.path == "/api/v1/device/approve" and method == "POST":
            return self._approve_device(headers, body, identity)
        if route.path.startswith("/api/v1/media/") and method in ("GET", "HEAD"):
            return self._media_response(
                route.path.removeprefix("/api/v1/media/"), method, headers, identity
            )
        if route.path == "/api/v1/uploads" and method == "POST":
            return self._begin_upload(headers, body, identity)
        if route.path.startswith("/api/v1/uploads/") and method == "PUT":
            return self._append_upload(
                route.path.removeprefix("/api/v1/uploads/"), headers, body, identity
            )
        if route.path == "/api/v1/staged-submissions" and method == "POST":
            return self._create_staged_submission(headers, body, identity)
        if (
            route.path.startswith("/api/v1/staged-submissions/")
            and route.path.endswith("/files")
            and method == "POST"
        ):
            return self._begin_staged_file(
                route.path.removeprefix("/api/v1/staged-submissions/").removesuffix(
                    "/files"
                ),
                headers,
                body,
                identity,
            )
        if (
            route.path.startswith("/api/v1/staged-submissions/")
            and route.path.endswith("/seal")
            and method == "POST"
        ):
            return self._seal_staged_submission(
                route.path.removeprefix("/api/v1/staged-submissions/").removesuffix(
                    "/seal"
                ),
                headers,
                identity,
            )
        if (
            route.path.startswith("/api/v1/staged-submissions/")
            and route.path.endswith("/process")
            and method == "POST"
        ):
            return self._process_staged_submission(
                route.path.removeprefix("/api/v1/staged-submissions/").removesuffix(
                    "/process"
                ),
                headers,
                identity,
            )
        if route.path.startswith("/api/v1/staged-submissions/") and method == "GET":
            return self._staged_submission_response(
                route.path.removeprefix("/api/v1/staged-submissions/"),
                headers,
                identity,
            )
        if route.path.startswith("/api/v1/staged-files/") and method == "PUT":
            return self._append_staged_file(
                route.path.removeprefix("/api/v1/staged-files/"),
                headers,
                body,
                identity,
            )
        science_routes = {
            "/api/v1/projects": ("projects", "project"),
            "/api/v1/phases": ("pm_phases", "phase"),
            "/api/v1/tasks": ("pm_tasks", "task"),
            "/api/v1/sprints": ("pm_sprints", "sprint"),
            "/api/v1/work-schedules": ("hr_work_schedules", "work_schedule"),
            "/api/v1/absences": ("hr_absences", "absence"),
            "/api/v1/obligations": ("hr_obligations", "obligation"),
            "/api/v1/allocations": ("pm_allocations", "allocation"),
            "/api/v1/dossiers": ("dossiers", "dossier"),
            "/api/v1/dossier-reviews": ("dossier_reviews", "dossier_review"),
            "/api/v1/observations": ("server_observations", "observation"),
            "/api/v1/specimens": ("pm_specimens", "specimen"),
            "/api/v1/encounters": ("pm_encounters", "encounter"),
            "/api/v1/protocols": ("pm_protocols", "protocol"),
            "/api/v1/survey-events": ("pm_survey_events", "survey_event"),
            "/api/v1/enrichments": ("pm_enrichments", "enrichment"),
            "/api/v1/samples": ("pm_samples", "sample"),
            "/api/v1/laboratory-records": ("pm_laboratory_records", "laboratory_record"),
            "/api/v1/reference-values": ("pm_reference_values", "reference_value"),
            "/api/v1/ai-providers": ("ai_providers", "ai_provider"),
            "/api/v1/ai-models": ("ai_models", "ai_model"),
            "/api/v1/mcp-servers": ("mcp_servers", "mcp_server"),
            "/api/v1/connectors": ("connectors", "connector"),
            "/api/v1/knowledge": ("server_knowledge", "knowledge"),
            "/api/v1/collections": ("server_collections", "collection"),
            "/api/v1/operations/assets": ("ops_equipment_assets", "operations_asset"),
            "/api/v1/operations/locations": ("ops_locations", "operations_location"),
            "/api/v1/operations/drawings": ("ops_building_drawings", "operations_drawing"),
            "/api/v1/operations/maintenance": ("ops_maintenance_events", "operations_maintenance"),
            "/api/v1/operations/calibrations": ("ops_calibration_events", "operations_calibration"),
            "/api/v1/operations/documents": ("ops_asset_documents", "operations_document"),
            "/api/v1/operations/storage-conditions": ("ops_storage_conditions", "operations_storage_condition"),
            "/api/v1/operations/drawing-markers": ("ops_drawing_markers", "operations_drawing_marker"),
            "/api/v1/operations/movements": ("ops_asset_movements", "operations_movement"),
        }
        if route.path in science_routes and method == "GET":
            collection, resource_type = science_routes[route.path]
            query = parse_qs(route.query)
            purpose = headers.get("x-fieldora-purpose", "research")
            project_filter = query.get("project_id", [""])[0]
            records = self._science.records(collection)
            disclosed = []
            for record in records:
                project_id = (
                    str(record.get("id", ""))
                    if collection == "projects"
                    else str(record.get("project_id", ""))
                )
                if project_filter and project_id != project_filter:
                    continue
                decision = self._decisions.decide(
                    AccessRequest(
                        subject_id=identity.identity_id,
                        action="view",
                        resource_type=resource_type,
                        resource_id=str(record.get("id", "")),
                        organization_id=identity.organization_id,
                        project_id=project_id,
                        purpose=purpose,
                    )
                )
                if decision.allowed:
                    disclosed.append(record)
            return ApiResponse.json(200, {"items": disclosed, "count": len(disclosed)})
        if route.path in science_routes and method == "POST":
            collection, resource_type = science_routes[route.path]
            if len(body) > 1_048_576:
                return ApiResponse.json(413, {"error": "request_too_large"})
            try:
                record = json.loads(body)
                resource_id = str(record["id"])
                project_id = (
                    resource_id if collection == "projects"
                    else str(record["project_id"])
                )
            except (KeyError, TypeError, json.JSONDecodeError):
                return ApiResponse.json(400, {"error": "invalid_request"})
            decision = self._decisions.decide(
                AccessRequest(
                    identity.identity_id, "edit", resource_type, resource_id,
                    identity.organization_id, project_id,
                    headers.get("x-fieldora-purpose", "research"),
                )
            )
            if not decision.allowed:
                return ApiResponse.json(403, {"error": "forbidden"})
            expected = headers.get("if-match")
            try:
                revision = self._science.put(
                    collection, record, None if expected is None else int(expected)
                )
            except ValueError:
                return ApiResponse.json(409, {"error": "revision_conflict"})
            return ApiResponse.json(200, {"item": record, "revision": revision})
        return ApiResponse.json(404, {"error": "not_found"})

    def _contract_decision(
        self,
        identity: Identity,
        headers: dict[str, str],
        contract_id: str,
        organization_id: str,
        project_id: str,
        action: str = "administer_contracts",
    ):
        return self._decisions.decide(
            AccessRequest(
                identity.identity_id, action, "contract",
                contract_id, organization_id, project_id,
                headers.get("x-fieldora-purpose", "administration"),
            )
        )

    def _media_list_response(
        self, query_string: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        if self._media is None:
            return ApiResponse.json(404, {"error": "not_found"})
        query = parse_qs(query_string)
        project_id = query.get("project_id", [""])[0]
        try:
            limit = max(1, min(int(query.get("limit", ["200"])[0]), 500))
        except ValueError:
            return ApiResponse.json(400, {"error": "invalid_limit"})
        items = []
        for record in self._media.records(identity.organization_id, project_id, limit * 2):
            decision = self._decisions.decide(
                AccessRequest(
                    identity.identity_id, "view", "asset", record.media_id,
                    record.organization_id, record.project_id,
                    headers.get("x-fieldora-purpose", "research"),
                )
            )
            if decision.allowed:
                items.append({
                    "media_id": record.media_id, "project_id": record.project_id,
                    "mime_type": record.mime_type, "size_bytes": record.size_bytes,
                    "sha256": record.sha256,
                    "download_url": f"/api/v1/media/{record.media_id}",
                })
            if len(items) == limit:
                break
        return ApiResponse.json(200, {"items": items, "count": len(items)})

    def _create_contract(
        self, headers: dict[str, str], body: bytes, identity: Identity
    ) -> ApiResponse:
        if self._access_repository is None or len(body) > 32_768:
            return ApiResponse.json(400, {"error": "invalid_request"})
        try:
            data = json.loads(body)
            organization_id = str(data["organization_id"])
            project_id = str(data["project_id"])
            if not self._contract_decision(
                identity, headers, "", organization_id, project_id
            ).allowed:
                return ApiResponse.json(403, {"error": "forbidden"})
            administration = AccessAdministrationService(self._access_repository)
            values = {
                "title": str(data["title"]),
                "organization_id": organization_id,
                "project_id": project_id,
                "subject_id": str(data["subject_id"]),
                "starts_at_utc": str(data["starts_at_utc"]),
                "ends_at_utc": str(data["ends_at_utc"]),
                "rights": tuple(str(item) for item in data["rights"]),
            }
            approval_required = data.get("approval_required", False)
            if not isinstance(approval_required, bool):
                raise ValueError
            if approval_required:
                required_approvals = data.get("required_approvals", 1)
                contract = administration.propose_project_contract_grant(
                    requested_by=identity.identity_id,
                    required_approvals=required_approvals,
                    **values,
                )
                policies = ()
            else:
                contract, policies = administration.create_project_contract_grant(
                    **values
                )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_contract"})
        return ApiResponse.json(
            201,
            {
                "contract": self._contract_payload(contract),
                "policy_ids": [item.policy_id for item in policies],
            },
        )

    def _contracts_response(
        self, query_string: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        if self._access_repository is None:
            return ApiResponse.json(404, {"error": "not_found"})
        query = parse_qs(query_string)
        try:
            limit = max(1, min(int(query.get("limit", ["100"])[0]), 200))
        except ValueError:
            return ApiResponse.json(400, {"error": "invalid_request"})
        after = query.get("after", [""])[0]
        items = []
        contracts = sorted(
            self._access_repository.contracts(), key=lambda item: item.contract_id
        )
        for contract in contracts:
            if contract.contract_id <= after:
                continue
            project_id = str(contract.terms.get("project_id", ""))
            if self._contract_decision(
                identity, headers, contract.contract_id,
                contract.organization_id, project_id,
            ).allowed:
                items.append(self._contract_payload(contract))
                if len(items) > limit:
                    break
        has_more = len(items) > limit
        disclosed = items[:limit]
        return ApiResponse.json(
            200,
            {
                "items": disclosed,
                "count": len(disclosed),
                "next_cursor": disclosed[-1]["contract_id"] if has_more else "",
            },
        )

    def _contract_approvals_response(
        self, query_string: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        """Return only proposals this identity may still approve."""
        if self._access_repository is None:
            return ApiResponse.json(404, {"error": "not_found"})
        query = parse_qs(query_string)
        try:
            limit = max(1, min(int(query.get("limit", ["100"])[0]), 200))
        except ValueError:
            return ApiResponse.json(400, {"error": "invalid_request"})
        after = query.get("after", [""])[0]
        items = []
        contracts = sorted(
            self._access_repository.contracts(), key=lambda item: item.contract_id
        )
        for contract in contracts:
            if contract.contract_id <= after or contract.status != "proposed":
                continue
            approvals = contract.terms.get("approvals", [])
            if contract.terms.get("requested_by") == identity.identity_id or any(
                item.get("approved_by") == identity.identity_id for item in approvals
            ):
                continue
            project_id = str(contract.terms.get("project_id", ""))
            if self._contract_decision(
                identity, headers, contract.contract_id,
                contract.organization_id, project_id, "approve_contracts",
            ).allowed:
                items.append(self._contract_payload(contract))
                if len(items) > limit:
                    break
        has_more = len(items) > limit
        disclosed = items[:limit]
        return ApiResponse.json(
            200,
            {
                "items": disclosed,
                "count": len(disclosed),
                "next_cursor": disclosed[-1]["contract_id"] if has_more else "",
            },
        )

    def _contract_expiry_response(
        self, query_string: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        """Return active, authorized contracts ending inside a review window."""
        if self._access_repository is None:
            return ApiResponse.json(404, {"error": "not_found"})
        query = parse_qs(query_string)
        try:
            limit = max(1, min(int(query.get("limit", ["100"])[0]), 200))
            within_days = int(query.get("within_days", ["30"])[0])
            if not 1 <= within_days <= 365:
                raise ValueError
        except ValueError:
            return ApiResponse.json(400, {"error": "invalid_request"})
        after = query.get("after", [""])[0]
        now = datetime.now(UTC)
        cutoff = now + timedelta(days=within_days)
        items = []
        contracts = sorted(
            self._access_repository.contracts(), key=lambda item: item.contract_id
        )
        for contract in contracts:
            if contract.contract_id <= after or contract.status != "active":
                continue
            try:
                parsed_end = datetime.fromisoformat(contract.ends_at_utc)
                if parsed_end.tzinfo is None:
                    continue
                ends_at = parsed_end.astimezone(UTC)
            except (TypeError, ValueError):
                continue
            if not now < ends_at <= cutoff:
                continue
            project_id = str(contract.terms.get("project_id", ""))
            if self._contract_decision(
                identity, headers, contract.contract_id,
                contract.organization_id, project_id,
            ).allowed:
                items.append(self._contract_payload(contract))
                if len(items) > limit:
                    break
        has_more = len(items) > limit
        disclosed = items[:limit]
        return ApiResponse.json(
            200,
            {
                "items": disclosed,
                "count": len(disclosed),
                "within_days": within_days,
                "next_cursor": disclosed[-1]["contract_id"] if has_more else "",
            },
        )

    def _contract_response(
        self, contract_id: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        contract = (
            None if self._access_repository is None
            else self._access_repository.contract(contract_id)
        )
        if contract is None:
            return ApiResponse.json(404, {"error": "not_found"})
        project_id = str(contract.terms.get("project_id", ""))
        if not self._contract_decision(
            identity, headers, contract.contract_id,
            contract.organization_id, project_id,
        ).allowed:
            return ApiResponse.json(404, {"error": "not_found"})
        return ApiResponse.json(200, {"contract": self._contract_payload(contract)})

    def _set_contract_status(
        self,
        contract_id: str,
        headers: dict[str, str],
        body: bytes,
        identity: Identity,
    ) -> ApiResponse:
        contract = (
            None if self._access_repository is None
            else self._access_repository.contract(contract_id)
        )
        if contract is None:
            return ApiResponse.json(404, {"error": "not_found"})
        project_id = str(contract.terms.get("project_id", ""))
        if not self._contract_decision(
            identity, headers, contract.contract_id,
            contract.organization_id, project_id,
        ).allowed:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            status = str(json.loads(body)["status"])
            updated = AccessAdministrationService(
                self._access_repository
            ).set_contract_status(contract_id, status)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_contract_status"})
        return ApiResponse.json(200, {"contract": self._contract_payload(updated)})

    def _approve_contract(
        self, contract_id: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        contract = (
            None if self._access_repository is None
            else self._access_repository.contract(contract_id)
        )
        if contract is None:
            return ApiResponse.json(404, {"error": "not_found"})
        project_id = str(contract.terms.get("project_id", ""))
        if not self._contract_decision(
            identity, headers, contract.contract_id,
            contract.organization_id, project_id, "approve_contracts",
        ).allowed:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            updated, policies = AccessAdministrationService(
                self._access_repository
            ).approve_project_contract_grant(
                contract.contract_id, identity.identity_id
            )
        except ValueError:
            return ApiResponse.json(409, {"error": "approval_conflict"})
        return ApiResponse.json(
            200,
            {
                "contract": self._contract_payload(updated),
                "policy_ids": [item.policy_id for item in policies],
                "approval_complete": updated.status == "active",
            },
        )

    @staticmethod
    def _contract_payload(contract) -> dict:
        return {
            "contract_id": contract.contract_id,
            "title": contract.title,
            "organization_id": contract.organization_id,
            "starts_at_utc": contract.starts_at_utc,
            "ends_at_utc": contract.ends_at_utc,
            "status": contract.status,
            "terms": contract.terms,
        }

    def _submit_job(
        self, headers: dict[str, str], body: bytes, identity: Identity
    ) -> ApiResponse:
        if self._jobs is None or len(body) > 16_384:
            return ApiResponse.json(400, {"error": "invalid_request"})
        try:
            data = json.loads(body)
            job_type = str(data["job_type"])
            if job_type not in ("rebuild_search", "export_project"):
                raise ValueError
            project_id = (
                str(data["project_id"]) if job_type == "export_project" else ""
            )
            if job_type == "export_project" and not project_id:
                raise ValueError
            include_references = data.get("include_library_references", False)
            if not isinstance(include_references, bool):
                raise ValueError
            recipient_public = data.get("recipient_public_key")
            if recipient_public is not None:
                from natureai_next.server.export_encryption import (
                    load_recipient_public_key,
                )

                if not isinstance(recipient_public, dict):
                    raise ValueError
                load_recipient_public_key(recipient_public)
            payload = (
                {
                    "include_library_references": include_references,
                    **(
                        {"recipient_public_key": recipient_public}
                        if recipient_public is not None else {}
                    ),
                }
                if job_type == "export_project" else {}
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_job"})
        action, resource_type, purpose = (
            ("export", "project", "research")
            if job_type == "export_project"
            else ("administer_search", "search_index", "administration")
        )
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id, action, resource_type, project_id,
                identity.organization_id, project_id,
                headers.get("x-fieldora-purpose", purpose),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})
        job = self._jobs.enqueue(
            job_type, identity.identity_id, identity.organization_id,
            project_id, payload,
        )
        return ApiResponse.json(
            202, {"job_id": job.job_id, "status": job.status}
        )

    def _export_response(
        self, export_id: str, method: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        record = None if self._exports is None else self._exports.record(export_id)
        if record is None:
            return ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id, "download_export", "project_export", export_id,
                record.organization_id, record.project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(404, {"error": "not_found"})
        start, end, status = 0, record.size_bytes - 1, 200
        requested = headers.get("range", "")
        if requested:
            try:
                unit, values = requested.split("=", 1)
                first, last = values.split("-", 1)
                if unit != "bytes" or "," in values:
                    raise ValueError
                start = int(first)
                end = record.size_bytes - 1 if not last else int(last)
                if start < 0 or end < start or end >= record.size_bytes:
                    raise ValueError
                status = 206
            except ValueError:
                return ApiResponse(
                    416, b"", "application/json",
                    (("Content-Range", f"bytes */{record.size_bytes}"),),
                )
        try:
            body = b"" if method == "HEAD" else self._exports.read_range(
                record, start, end
            )
        except FileNotFoundError:
            return ApiResponse.json(404, {"error": "not_found"})
        response_headers = [
            ("Accept-Ranges", "bytes"),
            ("Content-Length", str(end - start + 1)),
            ("Content-Disposition", f'attachment; filename="{record.filename}"'),
            ("ETag", f'"sha256-{record.sha256}"'),
            ("X-Content-SHA256", record.sha256),
        ]
        if status == 206:
            response_headers.append(
                ("Content-Range", f"bytes {start}-{end}/{record.size_bytes}")
            )
        content_type = (
            "application/vnd.fieldora.project-encrypted"
            if record.filename.endswith(".fieldora-encrypted")
            else "application/vnd.fieldora.project+zip"
        )
        return ApiResponse(
            status, body, content_type,
            tuple(response_headers),
        )

    def _revoke_export(
        self, export_id: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        record = None if self._exports is None else self._exports.record(export_id)
        if record is None:
            return ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id, "revoke_export", "project_export", export_id,
                record.organization_id, record.project_id,
                headers.get("x-fieldora-purpose", "administration"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(404, {"error": "not_found"})
        if not self._exports.revoke(export_id):
            return ApiResponse.json(404, {"error": "not_found"})
        return ApiResponse(204, b"")

    def _export_attestation(
        self, export_id: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        record = None if self._exports is None else self._exports.record(export_id)
        if record is None:
            return ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id, "download_export", "project_export", export_id,
                record.organization_id, record.project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(404, {"error": "not_found"})
        attestation = self._exports.attestation(record)
        if attestation is None:
            return ApiResponse.json(404, {"error": "not_found"})
        return ApiResponse.json(200, attestation)

    def _job_response(
        self, job_id: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        job = None if self._jobs is None else self._jobs.job(job_id)
        if job is None:
            return ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id, "view_job", "job", job.job_id,
                job.organization_id, job.project_id,
                headers.get("x-fieldora-purpose", "administration"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(404, {"error": "not_found"})
        return ApiResponse.json(
            200,
            {
                "job_id": job.job_id, "job_type": job.job_type,
                "status": job.status, "attempts": job.attempts,
                "result": job.result if job.status in ("succeeded", "failed") else {},
                "created_at_utc": job.created_at_utc,
                "updated_at_utc": job.updated_at_utc,
            },
        )

    def _search_response(
        self, query_string: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        if self._search is None:
            return ApiResponse.json(404, {"error": "not_found"})
        query = parse_qs(query_string)
        text = query.get("q", [""])[0].strip()
        try:
            limit = max(1, min(int(query.get("limit", ["25"])[0]), 100))
        except ValueError:
            return ApiResponse.json(400, {"error": "invalid_limit"})
        if len(text) < 2 or len(text) > 500:
            return ApiResponse.json(400, {"error": "invalid_query"})
        items = []
        for hit in self._search.candidates(text, limit * 5):
            decision = self._decisions.decide(
                AccessRequest(
                    identity.identity_id, "search", hit.resource_type, hit.resource_id,
                    hit.organization_id, hit.project_id,
                    headers.get("x-fieldora-purpose", "research"),
                )
            )
            if decision.allowed:
                items.append(
                    {
                        "resource_type": hit.resource_type,
                        "resource_id": hit.resource_id,
                        "project_id": hit.project_id,
                        "title": hit.title,
                        "snippet": hit.snippet,
                    }
                )
            if len(items) == limit:
                break
        return ApiResponse.json(200, {"items": items, "count": len(items)})

    def _audit_response(
        self, query_string: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        if self._audit_repository is None:
            return ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id, "view_audit", "security_audit", "",
                identity.organization_id, "",
                headers.get("x-fieldora-purpose", "administration"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})
        try:
            limit = max(1, min(int(parse_qs(query_string).get("limit", ["100"])[0]), 200))
        except ValueError:
            return ApiResponse.json(400, {"error": "invalid_limit"})
        events = []
        for event in self._audit_repository.audit_events(limit=limit * 2):
            request = json.loads(str(event["request_json"]))
            if (
                identity.attributes.get("platform_admin") != "true"
                and request.get("organization_id") != identity.organization_id
            ):
                continue
            events.append(
                {
                    "sequence": event["sequence"],
                    "occurred_at_utc": event["occurred_at_utc"],
                    "subject_id": event["subject_id"],
                    "action": event["action"],
                    "resource_type": event["resource_type"],
                    "resource_id": event["resource_id"],
                    "allowed": bool(event["allowed"]),
                    "reason": event["reason"],
                    "policy_ids": json.loads(str(event["policy_ids_json"])),
                }
            )
            if len(events) == limit:
                break
        verified, detail = self._audit_repository.verify_audit_chain()
        return ApiResponse.json(
            200, {"items": events, "count": len(events), "chain_verified": verified,
                  "chain_detail": detail}
        )

    def _begin_device(self, body: bytes) -> ApiResponse:
        if self._device_authorization is None or len(body) > 16_384:
            return ApiResponse.json(400, {"error": "invalid_request"})
        try:
            data = json.loads(body)
            code = self._device_authorization.begin(
                str(data["device_name"]), str(data["organization_id"]),
                str(data["project_id"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        return ApiResponse.json(
            201,
            {
                "device_code": code.device_code, "user_code": code.user_code,
                "expires_at_utc": code.expires_at_utc, "interval_seconds": 5,
            },
        )

    def _approve_device(
        self, headers: dict[str, str], body: bytes, identity: Identity
    ) -> ApiResponse:
        if self._device_authorization is None:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            user_code = str(json.loads(body)["user_code"])
            record = self._device_authorization.pending(user_code)
            if record is None:
                raise ValueError
            decision = self._decisions.decide(
                AccessRequest(
                    identity.identity_id, "enroll_device", "project",
                    str(record["project_id"]), str(record["organization_id"]),
                    str(record["project_id"]),
                    headers.get("x-fieldora-purpose", "administration"),
                )
            )
            if not decision.allowed:
                return ApiResponse.json(403, {"error": "forbidden"})
            device_id = self._device_authorization.approve(
                user_code, identity.identity_id
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_or_expired_code"})
        return ApiResponse.json(200, {"approved": True, "device_id": device_id})

    def _exchange_device(self, body: bytes) -> ApiResponse:
        if self._device_authorization is None:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            device_code = str(json.loads(body)["device_code"])
            credential_id, token = self._device_authorization.exchange(device_code)
        except DeviceAuthorizationPending:
            return ApiResponse.json(428, {"error": "authorization_pending"})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_or_expired_code"})
        return ApiResponse.json(
            201,
            {
                "credential_id": credential_id, "access_token": token,
                "token_type": "ApiKey",
            },
        )

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
                    identity.identity_id, "upload", "asset", "",
                    identity.organization_id, project_id,
                    headers.get("x-fieldora-purpose", "research"),
                )
            )
            if not decision.allowed:
                return ApiResponse.json(403, {"error": "forbidden"})
            upload = self._media.begin_upload(
                identity.identity_id, identity.organization_id, project_id,
                str(data["filename"]), str(data.get("mime_type", "")),
                int(data["size_bytes"]), str(data["sha256"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        return ApiResponse.json(
            201, {"upload_id": upload.upload_id, "received_bytes": 0}
        )

    def _create_staged_submission(
        self, headers: dict[str, str], body: bytes, identity: Identity
    ) -> ApiResponse:
        if self._staged_ingestion is None or len(body) > 16_384:
            return ApiResponse.json(400, {"error": "staged_ingestion_unavailable"})
        try:
            data = json.loads(body)
            project_id = str(data["project_id"])
            purpose = str(data.get("purpose") or headers.get("x-fieldora-purpose", "research"))
            decision = self._decisions.decide(
                AccessRequest(
                    identity.identity_id,
                    "upload",
                    "asset",
                    "",
                    identity.organization_id,
                    project_id,
                    purpose,
                )
            )
            if not decision.allowed:
                return ApiResponse.json(403, {"error": "forbidden"})
            contract_id = str(data.get("contract_id", "")).strip()
            if contract_id and self._access_repository is not None:
                contract = self._access_repository.contract(contract_id)
                if (
                    contract is None
                    or not contract.active_at(datetime.now(UTC).isoformat())
                    or contract.organization_id != identity.organization_id
                    or str(contract.terms.get("project_id", "")) != project_id
                ):
                    return ApiResponse.json(409, {"error": "inactive_or_mismatched_contract"})
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
        return ApiResponse.json(201, {"submission": self._staged_submission_payload(submission)})

    def _authorized_staged_submission(
        self,
        submission_id: str,
        headers: dict[str, str],
        identity: Identity,
        action: str,
    ):
        if self._staged_ingestion is None:
            return None
        submission = self._staged_ingestion.store.submission(submission_id)
        if submission is None or submission.organization_id != identity.organization_id:
            return None
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id,
                action,
                "asset",
                submission_id,
                submission.organization_id,
                submission.project_id,
                headers.get("x-fieldora-purpose", submission.purpose),
            )
        )
        return submission if decision.allowed else None

    def _begin_staged_file(
        self,
        submission_id: str,
        headers: dict[str, str],
        body: bytes,
        identity: Identity,
    ) -> ApiResponse:
        submission = self._authorized_staged_submission(
            submission_id, headers, identity, "upload"
        )
        if submission is None or len(body) > 16_384:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            data = json.loads(body)
            item = self._staged_ingestion.store.begin_file(
                submission_id,
                relative_path=str(data.get("relative_path") or data["filename"]),
                filename=str(data["filename"]),
                mime_type=str(data.get("mime_type", "")),
                expected_size=int(data["size_bytes"]),
                expected_sha256=str(data["sha256"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_staged_file"})
        return ApiResponse.json(
            201,
            {
                "staged_file_id": item.staged_file_id,
                "received_bytes": item.received_bytes,
                "state": item.state,
            },
        )

    def _append_staged_file(
        self,
        staged_file_id: str,
        headers: dict[str, str],
        body: bytes,
        identity: Identity,
    ) -> ApiResponse:
        if self._staged_ingestion is None or len(body) > 8 * 1024 * 1024:
            return ApiResponse.json(413, {"error": "chunk_too_large"})
        item = self._staged_ingestion.store.file(staged_file_id)
        if item is None:
            return ApiResponse.json(404, {"error": "not_found"})
        submission = self._authorized_staged_submission(
            item.submission_id, headers, identity, "upload"
        )
        if submission is None:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            value = headers["content-range"]
            unit, values = value.split(" ", 1)
            interval, total = values.split("/", 1)
            first, last = interval.split("-", 1)
            start, end = int(first), int(last)
            if (
                unit != "bytes"
                or int(total) != item.expected_size
                or end - start + 1 != len(body)
            ):
                raise ValueError
            updated = self._staged_ingestion.store.append(staged_file_id, start, body)
        except (KeyError, ValueError):
            return ApiResponse.json(409, {"error": "invalid_chunk"})
        return ApiResponse.json(
            200,
            {
                "complete": updated.state == "uploaded",
                "received_bytes": updated.received_bytes,
                "state": updated.state,
            },
        )

    def _seal_staged_submission(
        self, submission_id: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        submission = self._authorized_staged_submission(
            submission_id, headers, identity, "upload"
        )
        if submission is None:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            updated = self._staged_ingestion.seal_and_queue(submission_id)
        except ValueError:
            return ApiResponse.json(409, {"error": "submission_incomplete"})
        return ApiResponse.json(
            202, {"submission": self._staged_submission_payload(updated)}
        )

    def _process_staged_submission(
        self, submission_id: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        submission = self._authorized_staged_submission(
            submission_id, headers, identity, "upload"
        )
        if submission is None:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            job_ids = self._staged_ingestion.queue_processing(submission_id)
        except ValueError:
            return ApiResponse.json(409, {"error": "submission_not_validated"})
        return ApiResponse.json(202, {"job_ids": job_ids, "count": len(job_ids)})

    def _staged_submission_response(
        self, submission_id: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        submission = self._authorized_staged_submission(
            submission_id, headers, identity, "view"
        )
        if submission is None:
            return ApiResponse.json(404, {"error": "not_found"})
        files = self._staged_ingestion.store.files(submission_id)
        return ApiResponse.json(
            200,
            {
                "submission": self._staged_submission_payload(submission),
                "files": [
                    {
                        "staged_file_id": item.staged_file_id,
                        "relative_path": item.relative_path,
                        "state": item.state,
                        "received_bytes": item.received_bytes,
                        "expected_size": item.expected_size,
                        "detected_mime_type": item.detected_mime_type,
                        "validation": item.validation_json,
                        "media_id": item.media_id,
                    }
                    for item in files
                ],
            },
        )

    @staticmethod
    def _staged_submission_payload(submission) -> dict[str, object]:
        return {
            "submission_id": submission.submission_id,
            "subject_id": submission.subject_id,
            "organization_id": submission.organization_id,
            "project_id": submission.project_id,
            "contract_id": submission.contract_id,
            "purpose": submission.purpose,
            "publication_policy": submission.publication_policy,
            "state": submission.state,
            "expected_files": submission.expected_files,
            "received_files": submission.received_files,
            "total_bytes": submission.total_bytes,
            "created_at_epoch": submission.created_at_epoch,
            "updated_at_epoch": submission.updated_at_epoch,
        }

    def _append_upload(
        self, upload_id: str, headers: dict[str, str], body: bytes, identity: Identity
    ) -> ApiResponse:
        if self._media is None or len(body) > 8 * 1024 * 1024:
            return ApiResponse.json(413, {"error": "chunk_too_large"})
        upload = self._media.upload(upload_id)
        if upload is None or upload.subject_id != identity.identity_id:
            return ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id, "upload", "asset", upload_id,
                upload.organization_id, upload.project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(404, {"error": "not_found"})
        try:
            value = headers["content-range"]
            unit, values = value.split(" ", 1)
            interval, total = values.split("/", 1)
            first, last = interval.split("-", 1)
            start, end = int(first), int(last)
            if unit != "bytes" or int(total) != upload.expected_size:
                raise ValueError
            if end - start + 1 != len(body):
                raise ValueError
            result = self._media.append_upload(upload, start, body)
        except (KeyError, ValueError):
            return ApiResponse.json(409, {"error": "invalid_chunk"})
        if hasattr(result, "media_id"):
            return ApiResponse.json(
                201, {"complete": True, "media_id": result.media_id}
            )
        return ApiResponse.json(
            200, {"complete": False, "received_bytes": result.received_bytes}
        )

    def _media_response(
        self, media_id: str, method: str, headers: dict[str, str], identity: Identity
    ) -> ApiResponse:
        record = None if self._media is None else self._media.record(media_id)
        if record is None:
            return ApiResponse.json(404, {"error": "not_found"})
        decision = self._decisions.decide(
            AccessRequest(
                identity.identity_id, "download", "asset", media_id,
                record.organization_id, record.project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(404, {"error": "not_found"})
        start, end, status = 0, record.size_bytes - 1, 200
        requested = headers.get("range", "")
        if requested:
            try:
                unit, values = requested.split("=", 1)
                first, last = values.split("-", 1)
                if unit != "bytes" or "," in values:
                    raise ValueError
                start = int(first)
                end = record.size_bytes - 1 if not last else int(last)
                if start < 0 or end < start or end >= record.size_bytes:
                    raise ValueError
                status = 206
            except ValueError:
                return ApiResponse(
                    416, b"", "application/json",
                    (("Content-Range", f"bytes */{record.size_bytes}"),),
                )
        body = b"" if method == "HEAD" else self._media.read_range(record, start, end)
        response_headers = [
            ("Accept-Ranges", "bytes"),
            ("Content-Length", str(end - start + 1)),
            ("ETag", f'"sha256-{record.sha256}"'),
            ("X-Content-SHA256", record.sha256),
        ]
        if status == 206:
            response_headers.append(
                ("Content-Range", f"bytes {start}-{end}/{record.size_bytes}")
            )
        return ApiResponse(status, body, record.mime_type, tuple(response_headers))

    def _login(self, headers: dict[str, str], body: bytes) -> ApiResponse:
        if len(body) > 16_384:
            return ApiResponse.json(413, {"error": "request_too_large"})
        try:
            data = json.loads(body)
            rate_key = headers.get("x-forwarded-for", headers.get("remote-address", "local"))
            rate_key += ":" + str(data.get("username", "")).casefold()
            if not self._login_limiter.allow(rate_key):
                return ApiResponse.json(429, {"error": "rate_limited"})
            session = self._authentication.login(
                str(data["username"]), str(data["password"]),
                headers.get("user-agent", "web"),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_request"})
        except AuthenticationFailed:
            return ApiResponse.json(401, {"error": "invalid_credentials"})
        return ApiResponse.json(
            201,
            {
                "access_token": session.token,
                "token_type": "Bearer",
                "expires_at_utc": session.expires_at_utc,
            },
        )

    def _identity(self, headers: dict[str, str]) -> tuple[str, Identity]:
        value = headers.get("authorization", "")
        if value.startswith("ApiKey "):
            token = value[7:].strip()
            if not token:
                raise AuthenticationFailed("Service credential required")
            return token, self._authentication.authenticate_service_key(token)
        if not value.startswith("Bearer "):
            raise AuthenticationFailed("Bearer session or API key required")
        token = value[7:].strip()
        if not token:
            raise AuthenticationFailed("Bearer session required")
        if token.count(".") == 2 and self._oidc is not None:
            return token, self._oidc.authenticate(token)
        return token, self._authentication.authenticate(token)
