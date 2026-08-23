"""Governed HTTP API mixin for offline desktop/mobile synchronization."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.domain.synchronization import (
    AssertionState,
    PrimaryResolution,
    SyncApplyResult,
    SyncAssertion,
    SyncBundle,
)
from natureai_next.server.api import ApiResponse


class OfflineSyncRepository(Protocol):
    def apply_bundle(self, bundle: SyncBundle) -> SyncApplyResult: ...

    def assertions(
        self, organization_id: str, record_type: str, logical_record_id: str
    ) -> tuple[SyncAssertion, ...]: ...

    def resolve_primary(self, resolution: PrimaryResolution) -> None: ...

    def current_resolution(
        self,
        organization_id: str,
        record_type: str,
        logical_record_id: str,
        audience: str = "organization",
    ) -> PrimaryResolution | None: ...

    def presentation_assertion(
        self,
        organization_id: str,
        record_type: str,
        logical_record_id: str,
        audience: str = "organization",
    ) -> SyncAssertion | None: ...


class OfflineSyncApiMixin:
    """Mixin that routes sync endpoints before delegating to the existing API chain."""

    _offline_sync: OfflineSyncRepository | None

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        path = route.path
        if path == "/api/v1/sync/bundles" and method == "POST":
            return self._sync_apply_bundle(headers, body)
        if path == "/api/v1/sync/assertions" and method == "GET":
            return self._sync_assertions(headers, route.query)
        if path == "/api/v1/sync/resolutions" and method == "POST":
            return self._sync_resolve(headers, body)
        if path == "/api/v1/sync/presentation" and method == "GET":
            return self._sync_presentation(headers, route.query)
        return super().dispatch(method, target, headers, body)  # type: ignore[misc]

    def _sync_identity(self, headers: dict[str, str]):
        try:
            _token, identity = self._identity(headers)  # type: ignore[attr-defined]
        except AuthenticationFailed as exc:
            return None, ApiResponse.json(
                401, {"error": "unauthorized", "detail": str(exc)}
            )
        return identity, None

    def _sync_apply_bundle(
        self, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if self._offline_sync is None:
            return ApiResponse.json(503, {"error": "sync_unavailable"})
        if len(body) > 5 * 1024 * 1024:
            return ApiResponse.json(413, {"error": "request_too_large"})
        identity, error = self._sync_identity(headers)
        if error is not None:
            return error
        assert identity is not None
        try:
            bundle = _decode_bundle(json.loads(body))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_sync_bundle"})
        if (
            bundle.organization_id != identity.organization_id
            or bundle.source_identity_id != identity.identity_id
        ):
            return ApiResponse.json(403, {"error": "sync_identity_mismatch"})

        accepted: list[SyncAssertion] = []
        denied: list[str] = []
        for assertion in bundle.assertions:
            if (
                assertion.organization_id != identity.organization_id
                or assertion.author_identity_id != identity.identity_id
            ):
                denied.append(assertion.assertion_id)
                continue
            decision = self._decisions.decide(  # type: ignore[attr-defined]
                AccessRequest(
                    identity.identity_id,
                    "edit",
                    assertion.record_type,
                    assertion.logical_record_id,
                    assertion.organization_id,
                    assertion.project_id,
                    headers.get("x-fieldora-purpose", "research"),
                )
            )
            if not decision.allowed:
                denied.append(assertion.assertion_id)
                continue
            accepted.append(assertion)

        authorized_bundle = replace(bundle, assertions=tuple(accepted))
        result = self._offline_sync.apply_bundle(authorized_bundle)
        rejected = tuple(dict.fromkeys((*result.rejected_assertion_ids, *denied)))
        status = 202 if rejected else 200
        return ApiResponse.json(
            status,
            {
                "bundle_id": result.bundle_id,
                "inserted_assertion_ids": list(result.inserted_assertion_ids),
                "duplicate_assertion_ids": list(result.duplicate_assertion_ids),
                "conflict_record_ids": list(result.conflict_record_ids),
                "rejected_assertion_ids": list(rejected),
            },
        )

    def _sync_assertions(
        self, headers: dict[str, str], query_string: str
    ) -> ApiResponse:
        if self._offline_sync is None:
            return ApiResponse.json(503, {"error": "sync_unavailable"})
        identity, error = self._sync_identity(headers)
        if error is not None:
            return error
        assert identity is not None
        query = parse_qs(query_string)
        record_type = query.get("record_type", [""])[0].strip()
        logical_record_id = query.get("logical_record_id", [""])[0].strip()
        project_id = query.get("project_id", [""])[0].strip()
        if not record_type or not logical_record_id:
            return ApiResponse.json(400, {"error": "invalid_sync_query"})
        if not self._sync_allowed(
            identity,
            headers,
            action="view",
            record_type=record_type,
            logical_record_id=logical_record_id,
            project_id=project_id,
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        items = self._offline_sync.assertions(
            identity.organization_id, record_type, logical_record_id
        )
        disclosed = [
            _assertion_payload(item)
            for item in items
            if not project_id or item.project_id == project_id
        ]
        return ApiResponse.json(200, {"items": disclosed, "count": len(disclosed)})

    def _sync_resolve(
        self, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if self._offline_sync is None:
            return ApiResponse.json(503, {"error": "sync_unavailable"})
        if len(body) > 64 * 1024:
            return ApiResponse.json(413, {"error": "request_too_large"})
        identity, error = self._sync_identity(headers)
        if error is not None:
            return error
        assert identity is not None
        try:
            data = json.loads(body)
            resolution = PrimaryResolution(
                resolution_id=str(data["resolution_id"]).strip(),
                logical_record_id=str(data["logical_record_id"]).strip(),
                record_type=str(data["record_type"]).strip(),
                organization_id=identity.organization_id,
                project_id=str(data.get("project_id", "")).strip(),
                primary_assertion_id=str(data["primary_assertion_id"]).strip(),
                decided_by_identity_id=identity.identity_id,
                decided_at_utc=str(data["decided_at_utc"]).strip(),
                rationale=str(data["rationale"]).strip(),
                audience=str(data.get("audience", "organization")).strip(),
                previous_resolution_id=str(data.get("previous_resolution_id", "")).strip(),
            )
            if not all(
                (
                    resolution.resolution_id,
                    resolution.logical_record_id,
                    resolution.record_type,
                    resolution.primary_assertion_id,
                    resolution.decided_at_utc,
                    resolution.rationale,
                    resolution.audience,
                )
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return ApiResponse.json(400, {"error": "invalid_sync_resolution"})
        if not self._sync_allowed(
            identity,
            headers,
            action="resolve",
            record_type=resolution.record_type,
            logical_record_id=resolution.logical_record_id,
            project_id=resolution.project_id,
        ):
            return ApiResponse.json(403, {"error": "forbidden"})
        try:
            self._offline_sync.resolve_primary(resolution)
        except ValueError as exc:
            return ApiResponse.json(
                409, {"error": "resolution_conflict", "detail": str(exc)}
            )
        return ApiResponse.json(201, {"resolution": asdict(resolution)})

    def _sync_presentation(
        self, headers: dict[str, str], query_string: str
    ) -> ApiResponse:
        if self._offline_sync is None:
            return ApiResponse.json(503, {"error": "sync_unavailable"})
        identity, error = self._sync_identity(headers)
        if error is not None:
            return error
        assert identity is not None
        query = parse_qs(query_string)
        record_type = query.get("record_type", [""])[0].strip()
        logical_record_id = query.get("logical_record_id", [""])[0].strip()
        project_id = query.get("project_id", [""])[0].strip()
        audience = query.get("audience", ["organization"])[0].strip()
        if not record_type or not logical_record_id or not audience:
            return ApiResponse.json(400, {"error": "invalid_sync_query"})
        if not self._sync_allowed(
            identity,
            headers,
            action="view",
            record_type=record_type,
            logical_record_id=logical_record_id,
            project_id=project_id,
        ):
            return ApiResponse.json(404, {"error": "not_found"})
        assertion = self._offline_sync.presentation_assertion(
            identity.organization_id, record_type, logical_record_id, audience
        )
        resolution = self._offline_sync.current_resolution(
            identity.organization_id, record_type, logical_record_id, audience
        )
        return ApiResponse.json(
            200,
            {
                "assertion": None if assertion is None else _assertion_payload(assertion),
                "resolution": None if resolution is None else asdict(resolution),
                "requires_resolution": assertion is None,
            },
        )

    def _sync_allowed(
        self,
        identity: Any,
        headers: dict[str, str],
        *,
        action: str,
        record_type: str,
        logical_record_id: str,
        project_id: str,
    ) -> bool:
        decision = self._decisions.decide(  # type: ignore[attr-defined]
            AccessRequest(
                identity.identity_id,
                action,
                record_type,
                logical_record_id,
                identity.organization_id,
                project_id,
                headers.get("x-fieldora-purpose", "research"),
            )
        )
        return decision.allowed


def _decode_bundle(data: object) -> SyncBundle:
    if not isinstance(data, dict):
        raise ValueError("bundle must be an object")
    assertions_data = data.get("assertions")
    if not isinstance(assertions_data, list) or len(assertions_data) > 5000:
        raise ValueError("assertions must be a bounded list")
    assertions = tuple(_decode_assertion(item) for item in assertions_data)
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in metadata.items()
    ):
        raise ValueError("bundle metadata must contain strings")
    return SyncBundle(
        bundle_id=str(data["bundle_id"]).strip(),
        organization_id=str(data["organization_id"]).strip(),
        source_device_id=str(data["source_device_id"]).strip(),
        source_identity_id=str(data["source_identity_id"]).strip(),
        created_at_utc=str(data["created_at_utc"]).strip(),
        assertions=assertions,
        checkpoint=str(data.get("checkpoint", "")).strip(),
        metadata=dict(metadata),
    )


def _decode_assertion(data: object) -> SyncAssertion:
    if not isinstance(data, dict):
        raise ValueError("assertion must be an object")
    evidence_ids = data.get("evidence_ids", [])
    if not isinstance(evidence_ids, list) or len(evidence_ids) > 10_000:
        raise ValueError("evidence ids must be a bounded list")
    payload = data.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("assertion payload must be an object")
    return SyncAssertion(
        assertion_id=str(data["assertion_id"]).strip(),
        logical_record_id=str(data["logical_record_id"]).strip(),
        record_type=str(data["record_type"]).strip(),
        organization_id=str(data["organization_id"]).strip(),
        project_id=str(data.get("project_id", "")).strip(),
        author_identity_id=str(data["author_identity_id"]).strip(),
        device_id=str(data["device_id"]).strip(),
        created_at_utc=str(data["created_at_utc"]).strip(),
        payload=dict(payload),
        state=AssertionState(str(data.get("state", AssertionState.ALTERNATIVE.value))),
        source_bundle_id=str(data.get("source_bundle_id", "")).strip(),
        contract_id=str(data.get("contract_id", "")).strip(),
        evidence_ids=tuple(str(item).strip() for item in evidence_ids),
        parent_assertion_id=str(data.get("parent_assertion_id", "")).strip(),
    )


def _assertion_payload(assertion: SyncAssertion) -> dict[str, Any]:
    return {
        "assertion_id": assertion.assertion_id,
        "logical_record_id": assertion.logical_record_id,
        "record_type": assertion.record_type,
        "organization_id": assertion.organization_id,
        "project_id": assertion.project_id,
        "author_identity_id": assertion.author_identity_id,
        "device_id": assertion.device_id,
        "created_at_utc": assertion.created_at_utc,
        "payload": assertion.payload,
        "state": assertion.state.value,
        "source_bundle_id": assertion.source_bundle_id,
        "contract_id": assertion.contract_id,
        "evidence_ids": list(assertion.evidence_ids),
        "parent_assertion_id": assertion.parent_assertion_id,
    }
