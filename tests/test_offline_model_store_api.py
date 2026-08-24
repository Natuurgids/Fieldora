from __future__ import annotations

import json
from pathlib import Path

from natureai_next.server.offline_model_store_api import InstalledModelStore


def _receipt(root: Path, model_id: str = "bio-model", version: str = "1.2.3") -> Path:
    version_root = root / model_id / version
    version_root.mkdir(parents=True)
    receipt = {
        "id": f"{model_id}@{version}",
        "model_id": model_id,
        "name": "Biodiversity model",
        "version": version,
        "project_id": "platform",
        "provider_id": "fieldora-offline",
        "network": "offline",
        "status": "installed",
        "artifact_storage_id": f"model:{model_id}:{version}",
        "artifact_total_bytes": 123,
        "artifact_files": [
            {"path": "model/model.safetensors", "sha256": "a" * 64, "size_bytes": 100},
            {"path": "model/config.json", "sha256": "b" * 64, "size_bytes": 23},
        ],
        "source": "fieldora-bastion",
        "license_id": "test-license",
        "verification": "sha256-per-file",
        "manifest_signature": "unsigned",
        "signing_key_id": "",
    }
    (version_root / "FIELDORA-INSTALL.json").write_text(json.dumps(receipt), encoding="utf-8")
    return version_root


def test_installed_model_store_exposes_only_opaque_metadata(tmp_path: Path) -> None:
    version_root = _receipt(tmp_path / "models")

    records = InstalledModelStore(tmp_path / "models").records()

    assert len(records) == 1
    record = records[0]
    assert record["id"] == "bio-model@1.2.3"
    assert record["artifact_storage_id"] == "model:bio-model:1.2.3"
    assert record["formats"] == ["safetensors"]
    encoded = json.dumps(record)
    assert str(tmp_path) not in encoded
    assert str(version_root) not in encoded
    assert "artifact_files" not in record


def test_installed_model_store_preserves_signature_provenance(tmp_path: Path) -> None:
    version_root = _receipt(tmp_path / "models")
    path = version_root / "FIELDORA-INSTALL.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["manifest_signature"] = "ed25519"
    payload["signing_key_id"] = "ab" * 16
    path.write_text(json.dumps(payload), encoding="utf-8")

    record = InstalledModelStore(tmp_path / "models").records()[0]

    assert record["manifest_signature"] == "ed25519"
    assert record["signing_key_id"] == "ab" * 16


def test_installed_model_store_preserves_only_sanitized_signed_scan_provenance(
    tmp_path: Path,
) -> None:
    version_root = _receipt(tmp_path / "models")
    path = version_root / "FIELDORA-INSTALL.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["manifest_signature"] = "ed25519"
    payload["signing_key_id"] = "ab" * 16
    payload["malware_scan"] = {
        "result": "clean",
        "scanner": "clamav",
        "scanner_version": "1.4.0",
        "definitions": "daily-12345",
        "scanned_at": "2026-08-24T17:00:00Z",
        "file_count": 2,
        "raw_log": "must not be disclosed",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    record = InstalledModelStore(tmp_path / "models").records()[0]

    assert record["malware_scan"] == {
        "result": "clean",
        "scanner": "clamav",
        "scanner_version": "1.4.0",
        "definitions": "daily-12345",
        "scanned_at": "2026-08-24T17:00:00Z",
        "file_count": 2,
    }
    assert "raw_log" not in json.dumps(record)


def test_installed_model_store_rejects_unsigned_scan_claim(tmp_path: Path) -> None:
    version_root = _receipt(tmp_path / "models")
    path = version_root / "FIELDORA-INSTALL.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["malware_scan"] = {
        "result": "clean",
        "scanner": "clamav",
        "scanner_version": "1.4.0",
        "definitions": "daily-12345",
        "scanned_at": "2026-08-24T17:00:00Z",
        "file_count": 2,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert InstalledModelStore(tmp_path / "models").records() == ()


def test_installed_model_store_rejects_receipt_identity_mismatch(tmp_path: Path) -> None:
    version_root = _receipt(tmp_path / "models")
    path = version_root / "FIELDORA-INSTALL.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["artifact_storage_id"] = "model:other:9"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert InstalledModelStore(tmp_path / "models").records() == ()


def test_installed_model_store_ignores_symlinked_version(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    _receipt(real_root)
    models = tmp_path / "models"
    (models / "bio-model").mkdir(parents=True)
    link = models / "bio-model" / "1.2.3"
    try:
        link.symlink_to(real_root / "bio-model" / "1.2.3", target_is_directory=True)
    except OSError:
        return

    assert InstalledModelStore(models).records() == ()
