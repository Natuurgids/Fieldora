from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

from natureai_next.server.storage_service_agent import LinkedStorageAgent, StorageAgentConfig


class _Exchange:
    def __init__(self, *, fail_first_catalogue: bool = False) -> None:
        self.sources: list[object] = []
        self.catalogue_payloads: list[dict] = []
        self.claim_items: list[dict] = []
        self.uploads: list[dict] = []
        self.completions: list[dict] = []
        self._fail_first_catalogue = fail_first_catalogue

    def register_source(self, source):
        self.sources.append(source)
        return {"storage_id": source.storage_id}

    def submit_catalogue(self, payload):
        self.catalogue_payloads.append(payload)
        if self._fail_first_catalogue:
            self._fail_first_catalogue = False
            raise RuntimeError("uncertain network failure")
        return {"batch_id": payload["batch_id"]}

    def claim_previews(self, payload):
        return {"items": list(self.claim_items)}

    def upload_preview(self, payload: bytes, **kwargs):
        self.uploads.append({"payload": payload, **kwargs})
        return {
            "media_id": kwargs["media_id"],
            "thumbnail_etag": kwargs["sha256"],
            "state": "ready",
        }

    def complete_preview(self, payload):
        self.completions.append(payload)
        return {"media_id": payload["media_id"]}


def _config(tmp_path: Path) -> StorageAgentConfig:
    root = tmp_path / "archive"
    root.mkdir()
    trust = tmp_path / "trust"
    trust.mkdir()
    certificate = trust / "service.crt"
    private_key = trust / "service.key"
    ca = trust / "ca.pem"
    for path in (certificate, private_key, ca):
        path.write_text("test", encoding="utf-8")
    return StorageAgentConfig(
        endpoint="https://fieldora-server:8766",
        service_id="storage-service-1",
        organization_id="org-1",
        storage_id="archive-1",
        display_name="Scientific archive",
        root_alias="primary-archive",
        root_path=root,
        state_root=tmp_path / "state",
        certificate=certificate,
        private_key=private_key,
        ca_certificate=ca,
        project_id="project-1",
    )


def test_catalogue_registers_only_opaque_source_and_completes_hash_chain(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.root_path / "a.txt").write_text("a", encoding="utf-8")
    (config.root_path / "b.txt").write_text("b", encoding="utf-8")
    exchange = _Exchange()
    agent = LinkedStorageAgent(config, exchange)

    state = agent.catalogue(batch_size=1)

    assert state.state == "completed"
    assert len(exchange.sources) == 1
    assert exchange.sources[0].root_alias == "primary-archive"
    assert not hasattr(exchange.sources[0], "root_path")
    assert [item["sequence"] for item in exchange.catalogue_payloads] == [1, 2, 3]
    assert exchange.catalogue_payloads[-1]["final"] is True
    assert exchange.catalogue_payloads[1]["previous_batch_sha256"] == exchange.catalogue_payloads[0]["batch_sha256"]
    assert exchange.catalogue_payloads[0]["items"][0]["project_id"] == "project-1"


def test_uncertain_catalogue_delivery_replays_identical_pending_batch(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.root_path / "image.txt").write_text("evidence", encoding="utf-8")
    first_exchange = _Exchange(fail_first_catalogue=True)
    first_agent = LinkedStorageAgent(config, first_exchange)

    with pytest.raises(RuntimeError, match="uncertain network failure"):
        first_agent.catalogue(batch_size=1)
    pending = first_exchange.catalogue_payloads[0]

    second_exchange = _Exchange()
    second_agent = LinkedStorageAgent(config, second_exchange)
    state = second_agent.catalogue(batch_size=1)

    assert second_exchange.catalogue_payloads[0] == pending
    assert state.state == "completed"


def test_priority_preview_lease_uploads_local_thumbnail_bytes(tmp_path: Path) -> None:
    config = _config(tmp_path)
    image_path = config.root_path / "camera" / "image.jpg"
    image_path.parent.mkdir()
    Image.new("RGB", (1200, 800)).save(image_path, "JPEG")
    exchange = _Exchange()
    agent = LinkedStorageAgent(config, exchange)
    agent.catalogue(batch_size=100)
    local = agent.repository.media_in_path(config.storage_id)[0]
    media_id = f"linked:{config.storage_id}:{local.media_id}"
    exchange.claim_items = [
        {
            "media_id": media_id,
            "storage_id": config.storage_id,
            "object_id": local.media_id,
            "organization_id": config.organization_id,
            "priority": 900,
            "reason": "visible-directory",
            "requested_by": "researcher-1",
            "worker_id": "preview-worker-1",
        }
    ]

    assert agent.process_preview_leases(worker_id="preview-worker-1") == 1
    assert exchange.completions == []
    assert len(exchange.uploads) == 1
    upload = exchange.uploads[0]
    assert upload["media_id"] == media_id
    assert upload["storage_id"] == config.storage_id
    assert upload["worker_id"] == "preview-worker-1"
    assert upload["payload"].startswith(b"\xff\xd8")
    assert hashlib.sha256(upload["payload"]).hexdigest() == upload["sha256"]
    updated = agent.repository.media(local.media_id)
    assert updated is not None and updated.thumbnail_state == "ready"
    assert (agent.preview_root / updated.thumbnail_key).is_file()
