from __future__ import annotations

import json
from uuid import UUID

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import Identity, IdentityKind
from natureai_next.server.api import ApiResponse
from natureai_next.server.linked_storage_operator_api import LinkedStorageOperatorApiMixin
from natureai_next.server.operator_control import ServiceRecord, ServiceState


class _BaseApi:
    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes):
        return ApiResponse.json(404, {"error": "not_found"})


class _Operator:
    def __init__(self) -> None:
        self.enrollments: list[dict[str, object]] = []

    def enroll(self, **kwargs):
        self.enrollments.append(dict(kwargs))
        return ServiceRecord(
            service_id=str(kwargs["service_id"]),
            organization_id=str(kwargs["organization_id"]),
            name=str(kwargs["name"]),
            service_type=str(kwargs["service_type"]),
            node_name=str(kwargs["node_name"]),
            state=ServiceState.ENROLLED.value,
            software_version=str(kwargs["software_version"]),
            configuration_sha256=str(kwargs["configuration_sha256"]),
            certificate_serial=str(kwargs["certificate_serial"]),
            certificate_not_after_epoch=int(kwargs["certificate_not_after_epoch"]),
            enrolled_at_epoch=1,
            last_heartbeat_epoch=1,
            drain_requested_epoch=0,
            stopped_at_epoch=0,
            revoked_at_epoch=0,
        )


class _Api(LinkedStorageOperatorApiMixin, _BaseApi):
    def __init__(self, *, allowed: bool = True) -> None:
        self._operator = _Operator()
        self.allowed = allowed
        self.identity = Identity("operator-1", IdentityKind.USER, "Operator", "org-1")
        self.operator_checks: list[tuple[str, str]] = []

    def _identity(self, headers):
        if headers.get("authorization") != "Bearer good-token":
            raise AuthenticationFailed("invalid token")
        return "good-token", self.identity

    def _allow_operator(self, _identity, _headers, action: str, resource_id: str) -> bool:
        self.operator_checks.append((action, resource_id))
        return self.allowed


def _headers() -> dict[str, str]:
    return {
        "authorization": "Bearer good-token",
        "x-fieldora-purpose": "administration",
    }


def test_operator_prepares_server_generated_opaque_storage_service_id() -> None:
    api = _Api()
    response = api.dispatch(
        "POST",
        "/api/v1/operator/linked-storage-services/prepare-id",
        _headers(),
        b"{}",
    )

    assert response.status == 200
    payload = json.loads(response.body)
    service_id = payload["service_id"]
    assert str(UUID(service_id)) == service_id
    assert api.operator_checks == [("service.enroll", "")]
    assert api._operator.enrollments == []


def test_operator_enrolls_prepared_id_as_linked_storage_only() -> None:
    api = _Api()
    service_id = "8da232a5-0b96-4d2f-882a-909e58d0b984"
    body = json.dumps(
        {
            "service_id": service_id,
            "name": "Archive node",
            "node_name": "archive-node-01",
            "certificate_serial": "abc123",
            "certificate_not_after_epoch": 4_000_000_000,
            "service_type": "api",
            "root_path": "D:/must-not-be-consumed",
            "credential": "must-not-be-consumed",
        }
    ).encode()

    response = api.dispatch(
        "POST", "/api/v1/operator/linked-storage-services", _headers(), body
    )

    assert response.status == 201
    payload = json.loads(response.body)
    assert payload["service"]["service_id"] == service_id
    assert payload["service"]["service_type"] == "linked-storage"
    assert len(api._operator.enrollments) == 1
    enrollment = api._operator.enrollments[0]
    assert enrollment["service_id"] == service_id
    assert enrollment["organization_id"] == "org-1"
    assert enrollment["service_type"] == "linked-storage"
    assert "root_path" not in enrollment
    assert "credential" not in enrollment


def test_linked_storage_enrollment_rejects_unprepared_identity_shape() -> None:
    api = _Api()
    body = json.dumps(
        {
            "service_id": "D:/archive",
            "name": "Archive node",
            "node_name": "archive-node-01",
            "certificate_serial": "abc123",
            "certificate_not_after_epoch": 4_000_000_000,
        }
    ).encode()

    response = api.dispatch(
        "POST", "/api/v1/operator/linked-storage-services", _headers(), body
    )

    assert response.status == 400
    assert api._operator.enrollments == []


def test_linked_storage_identity_bootstrap_is_pbac_and_auth_guarded() -> None:
    denied = _Api(allowed=False)
    response = denied.dispatch(
        "POST",
        "/api/v1/operator/linked-storage-services/prepare-id",
        _headers(),
        b"{}",
    )
    assert response.status == 403

    unauthorized = _Api().dispatch(
        "POST",
        "/api/v1/operator/linked-storage-services/prepare-id",
        {},
        b"{}",
    )
    assert unauthorized.status == 401
