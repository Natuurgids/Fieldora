from __future__ import annotations

import hashlib
from pathlib import Path

from natureai_next.server.storage_range_agent import LinkedStorageRangeAgent
from natureai_next.server.storage_service_agent import StorageAgentConfig


class _Exchange:
    def __init__(self) -> None:
        self.catalogue_payloads: list[dict] = []
        self.range_items: list[dict] = []
        self.uploads: list[dict] = []

    def register_source(self, source):
        return {"storage_id": source.storage_id}

    def submit_catalogue(self, payload):
        self.catalogue_payloads.append(payload)
        return {"batch_id": payload["batch_id"]}

    def claim_previews(self, payload):
        return {"items": []}

    def complete_preview(self, payload):
        return payload

    def upload_preview(self, payload: bytes, **kwargs):
        return {"media_id": kwargs["media_id"]}

    def claim_ranges(self, payload):
        return {"items": list(self.range_items)}

    def upload_range(self, payload: bytes, **kwargs):
        self.uploads.append({"payload": payload, **kwargs})
        return {"request_id": kwargs["request_id"], "state": "ready"}


def _config(tmp_path: Path) -> StorageAgentConfig:
    root = tmp_path / "archive"
    root.mkdir()
    trust = tmp_path / "trust"
    trust.mkdir()
    cert = trust / "service.crt"
    key = trust / "service.key"
    ca = trust / "ca.pem"
    for path in (cert, key, ca):
        path.write_text("test", encoding="utf-8")
    return StorageAgentConfig(
        endpoint="https://fieldora-server:8766",
        service_id="storage-service-1",
        organization_id="org-1",
        storage_id="archive-1",
        display_name="Archive",
        root_alias="archive",
        root_path=root,
        state_root=tmp_path / "state",
        certificate=cert,
        private_key=key,
        ca_certificate=ca,
        project_id="project-1",
    )


def test_range_worker_reads_only_leased_slice_and_uploads_digest(tmp_path: Path) -> None:
    config = _config(tmp_path)
    original = bytes(range(64))
    (config.root_path / "original.bin").write_bytes(original)
    exchange = _Exchange()
    agent = LinkedStorageRangeAgent(config, exchange)
    agent.catalogue(batch_size=100)
    local = agent.repository.media_in_path(config.storage_id)[0]
    exchange.range_items = [
        {
            "request_id": "range-request-1",
            "media_id": f"linked:{config.storage_id}:{local.media_id}",
            "storage_id": config.storage_id,
            "object_id": local.media_id,
            "organization_id": config.organization_id,
            "start_byte": 10,
            "end_byte": 19,
            "total_size": len(original),
            "mime_type": "application/octet-stream",
            "worker_id": "worker-1",
        }
    ]

    assert agent.process_range_leases(worker_id="worker-1") == 1
    assert len(exchange.uploads) == 1
    upload = exchange.uploads[0]
    assert upload["payload"] == original[10:20]
    assert upload["start_byte"] == 10
    assert upload["end_byte"] == 19
    assert upload["request_id"] == "range-request-1"
    assert hashlib.sha256(upload["payload"]).hexdigest() == upload["sha256"]


def test_range_worker_skips_file_if_catalogued_size_changed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    path = config.root_path / "original.bin"
    path.write_bytes(b"0123456789")
    exchange = _Exchange()
    agent = LinkedStorageRangeAgent(config, exchange)
    agent.catalogue(batch_size=100)
    local = agent.repository.media_in_path(config.storage_id)[0]
    path.write_bytes(b"changed-size")
    exchange.range_items = [
        {
            "request_id": "range-request-1",
            "media_id": f"linked:{config.storage_id}:{local.media_id}",
            "storage_id": config.storage_id,
            "object_id": local.media_id,
            "organization_id": config.organization_id,
            "start_byte": 0,
            "end_byte": 4,
            "total_size": local.size_bytes,
            "mime_type": "application/octet-stream",
            "worker_id": "worker-1",
        }
    ]

    assert agent.process_range_leases(worker_id="worker-1") == 0
    assert exchange.uploads == []
