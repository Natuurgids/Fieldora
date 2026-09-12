from __future__ import annotations

import json

from natureai_next.server.operator_control import ServiceRecord, ServiceState
from natureai_next.server.storage_exchange import StorageSourceRegistration
from natureai_next.server.storage_service_api import LinkedStorageServiceApi


class _Operators:
    def __init__(self) -> None:
        self._service = ServiceRecord(
            service_id="storage-service-1",
            organization_id="org-1",
            name="Archive service",
            service_type="linked-storage",
            node_name="storage-node-1",
            state=ServiceState.ACTIVE.value,
            software_version="5.4.0",
            configuration_sha256="",
            certificate_serial="ABCD",
            certificate_not_after_epoch=2_000_000_000,
            enrolled_at_epoch=1,
            last_heartbeat_epoch=2_000_000_000,
            drain_requested_epoch=0,
            stopped_at_epoch=0,
            revoked_at_epoch=0,
        )

    def service(self, service_id: str):
        return self._service if service_id == self._service.service_id else None

    def heartbeat(self, service_id: str, **_kwargs):
        if service_id != self._service.service_id:
            raise KeyError(service_id)
        return self._service


class _Catalogue:
    def __init__(self) -> None:
        self.registered: list[StorageSourceRegistration] = []

    def register_source(self, source: StorageSourceRegistration) -> None:
        self.registered.append(source)

    def source(self, _storage_id: str):
        return None


class _Leases:
    pass


def test_mtls_storage_api_rejects_writable_source_registration() -> None:
    catalogue = _Catalogue()
    api = LinkedStorageServiceApi(catalogue, _Leases(), _Operators())
    payload = json.dumps(
        {
            "storage_id": "archive-1",
            "organization_id": "org-1",
            "service_id": "storage-service-1",
            "display_name": "Scientific archive",
            "root_alias": "primary-archive",
            "read_only": False,
        }
    ).encode()

    response = api.dispatch(
        "POST",
        "/internal/v1/storage/sources",
        {"fieldora-peer-certificate-serial": "ABCD"},
        payload,
    )

    assert response.status == 400
    assert json.loads(response.body)["error"] == "invalid_storage_source"
    assert catalogue.registered == []
