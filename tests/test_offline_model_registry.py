from __future__ import annotations

import json
from pathlib import Path

from natureai_next.server.offline_model_registry import discover_offline_models


def test_discovers_sanitized_verified_receipt_without_path_disclosure(tmp_path: Path) -> None:
    receipt_dir = tmp_path / "models" / "bird-model" / "1.2.3"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "FIELDORA-INSTALL.json").write_text(
        json.dumps(
            {
                "id": "bird-model",
                "name": "Bird model",
                "version": "1.2.3",
                "provider_id": "fieldora-offline",
                "network": "offline",
                "enabled": True,
                "status": "installed",
                "artifact_storage_id": "model:bird-model:1.2.3",
                "artifact_total_bytes": 42,
                "artifact_files": [
                    {
                        "path": "model/model.safetensors",
                        "sha256": "a" * 64,
                        "size_bytes": 42,
                    }
                ],
                "source": "FieldoraBastion",
                "license_id": "test-license",
                "verification": "sha256-per-file",
                "artifact_store_path": "D:/secret/models/bird-model/1.2.3",
            }
        ),
        encoding="utf-8",
    )

    items = discover_offline_models(tmp_path / "models")

    assert len(items) == 1
    item = items[0]
    assert item["id"] == "bird-model"
    assert item["artifact_storage_id"] == "model:bird-model:1.2.3"
    assert item["formats"] == ["safetensors"]
    assert "artifact_store_path" not in item
    assert "artifact_files" not in item
    assert "D:/secret" not in json.dumps(item)


def test_ignores_receipt_with_inconsistent_opaque_storage_id(tmp_path: Path) -> None:
    receipt_dir = tmp_path / "models" / "bird-model" / "1.2.3"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "FIELDORA-INSTALL.json").write_text(
        json.dumps(
            {
                "id": "bird-model",
                "version": "1.2.3",
                "artifact_storage_id": "model:other:9",
                "artifact_files": [{"path": "model.gguf"}],
            }
        ),
        encoding="utf-8",
    )

    assert discover_offline_models(tmp_path / "models") == ()
