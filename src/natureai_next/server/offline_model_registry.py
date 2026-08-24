"""Discover verified offline model install receipts without exposing filesystem paths."""

from __future__ import annotations

import json
from pathlib import Path

_SAFE_FIELDS = {
    "id",
    "name",
    "version",
    "provider_id",
    "network",
    "enabled",
    "status",
    "artifact_storage_id",
    "artifact_total_bytes",
    "source",
    "license_id",
    "verification",
}
_MODEL_EXTENSIONS = {".safetensors", ".onnx", ".gguf"}


def discover_offline_models(model_store: Path) -> tuple[dict[str, object], ...]:
    """Return sanitized install receipts from a read-only model store."""
    root = model_store.resolve()
    if not root.is_dir():
        return ()
    discovered: list[dict[str, object]] = []
    for receipt_path in sorted(root.glob("*/*/FIELDORA-INSTALL.json")):
        if receipt_path.is_symlink() or not receipt_path.is_file():
            continue
        try:
            resolved = receipt_path.resolve(strict=True)
            resolved.relative_to(root)
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        model_id = str(payload.get("id") or "").strip()
        version = str(payload.get("version") or "").strip()
        storage_id = str(payload.get("artifact_storage_id") or "").strip()
        if not model_id or not version or storage_id != f"model:{model_id}:{version}":
            continue
        files = payload.get("artifact_files")
        if not isinstance(files, list):
            continue
        formats = sorted(
            {
                Path(str(item.get("path") or "")).suffix.lower().removeprefix(".")
                for item in files
                if isinstance(item, dict)
                and Path(str(item.get("path") or "")).suffix.lower() in _MODEL_EXTENSIONS
            }
        )
        if not formats:
            continue
        record = {key: payload[key] for key in _SAFE_FIELDS if key in payload}
        record["model_id"] = model_id
        record["formats"] = formats
        discovered.append(record)
    return tuple(discovered)
