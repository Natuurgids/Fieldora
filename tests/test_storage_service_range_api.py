from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from natureai_next.server.operator_control import ServiceRecord, ServiceState
from natureai_next.server.postgres_linked_range_transfer import LinkedRangeLease, LinkedRangeResult
from natureai_next.server.storage_exchange import StorageSourceRegistration
from natureai_next.server.storage_service_api import LinkedStorageServiceApi


class _Operators:
    def __init__(self) -> None:
        self.record = ServiceRecord(
            service_id="storage-service-1",
            organization_id="org-1",
            name="Archive",
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
        return self.record if service_id == self.record.service_id else None

    def heartbeat(self, service_id: str, **kwargs):
        self.record = replace(self.record, last_heartbeat_epoch=int(kwargs["now_epoch"]))
        return self.record


class _Catalogue:
    def source(self, storage_id: str):
        if storage_id != "archive-1":
            return None
        return StorageSourceRegistration(
            "archive-1", "org-1", "storage-service-1", "Archive", "primary-archive", True
        )


class _Leases:
    pass


class _Ranges:
    def __init__(self) -> None:
        self.claims: list[dict] = []
        self.uploads: list[dict] = []

    def claim(self, **kwargs):
        self.claims.append(kwargs)
        return (
            LinkedRangeLease(
                "request-1",
                "linked:archive-1:object-1",
                "archive-1",
                "object-1",
                "org-1",
                5,
                9,
                20,
                "application/octet-stream",
                kwargs["worker_id"],
            ),
        )

    def put_leased_range(self, **kwargs):
        self.uploads.append(kwargs)
        return LinkedRangeResult(
            kwargs["request_id"],
            kwargs["media_id"],
            kwargs["organization_id"],
            "researcher-1",
            kwargs["start_byte"],
            kwargs["end_byte"],
            20,
            "application/octet-stream",
            "ready",
            kwargs["sha256"],
            kwargs["payload"],
            2_000_000_000,
        )


def _api():
    ranges = _Ranges()
    api = LinkedStorageServiceApi(
        _Catalogue(), _Leases(), _Operators(), range_transfers=ranges
    )
    return api, ranges


def _peer(serial: str = "ABCD") -> dict[str, str]:
    return {"fieldora-peer-certificate-serial": serial}


def _claim() -> bytes:
    return json.dumps(
        {
            "service_id": "storage-service-1",
            "organization_id": "org-1",
            "storage_id": "archive-1",
            "worker_id": "range-worker-1",
            "limit": 8,
            "lease_seconds": 120,
        }
    ).encode()


def _upload_headers(payload: bytes, serial: str = "ABCD") -> dict[str, str]:
    return {
        **_peer(serial),
        "fieldora-service-id": "storage-service-1",
        "fieldora-organization-id": "org-1",
        "fieldora-storage-id": "archive-1",
        "fieldora-worker-id": "range-worker-1",
        "fieldora-media-id": "linked:archive-1:object-1",
        "fieldora-range-request-id": "request-1",
        "fieldora-range-start": "5",
        "fieldora-range-end": "9",
        "fieldora-range-sha256": hashlib.sha256(payload).hexdigest(),
        "content-type": "application/octet-stream",
    }


def test_range_claim_is_bound_to_enrolled_storage_certificate() -> None:
    api, ranges = _api()
    denied = api.dispatch(
        "POST", "/internal/v1/storage/ranges/claim", _peer("FFFF"), _claim()
    )
    assert denied.status == 403
    assert ranges.claims == []

    accepted = api.dispatch(
        "POST", "/internal/v1/storage/ranges/claim", _peer(), _claim()
    )
    assert accepted.status == 200
    assert ranges.claims[0]["worker_id"] == "range-worker-1"
    assert json.loads(accepted.body)["items"][0]["request_id"] == "request-1"


def test_range_upload_rejects_wrong_certificate_before_storing_bytes() -> None:
    api, ranges = _api()
    payload = b"56789"
    denied = api.dispatch(
        "PUT",
        "/internal/v1/storage/ranges/upload",
        _upload_headers(payload, "FFFF"),
        payload,
    )
    assert denied.status == 403
    assert ranges.uploads == []

    accepted = api.dispatch(
        "PUT", "/internal/v1/storage/ranges/upload", _upload_headers(payload), payload
    )
    assert accepted.status == 200
    assert ranges.uploads[0]["payload"] == payload
    assert ranges.uploads[0]["start_byte"] == 5
    assert ranges.uploads[0]["end_byte"] == 9
    assert ranges.uploads[0]["sha256"] == hashlib.sha256(payload).hexdigest()
