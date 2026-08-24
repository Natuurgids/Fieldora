"""PBAC-governed discovery of installed offline model artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse

_RECEIPT_NAME = "FIELDORA-INSTALL.json"
_MAX_RECEIPT_BYTES = 1_048_576
_MAX_MODELS = 200
_ALLOWED_FORMATS = {".safetensors", ".onnx", ".gguf"}


class InstalledModelStore:
    """Read bounded, browser-safe receipts from a read-only model store."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def records(self) -> tuple[dict[str, object], ...]:
        if not self._root.is_dir() or self._root.is_symlink():
            return ()
        records: list[dict[str, object]] = []
        for model_dir in sorted(self._root.iterdir(), key=lambda path: path.name):
            if len(records) >= _MAX_MODELS:
                break
            if model_dir.is_symlink() or not model_dir.is_dir():
                continue
            for version_dir in sorted(model_dir.iterdir(), key=lambda path: path.name):
                if len(records) >= _MAX_MODELS:
                    break
                if version_dir.is_symlink() or not version_dir.is_dir():
                    continue
                receipt = version_dir / _RECEIPT_NAME
                record = _read_receipt(receipt, model_dir.name, version_dir.name)
                if record is not None:
                    records.append(record)
        return tuple(records)


def _read_receipt(path: Path, model_id: str, version: str) -> dict[str, object] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        if path.stat().st_size > _MAX_RECEIPT_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    registry_id = f"{model_id}@{version}"
    storage_id = f"model:{model_id}:{version}"
    if (
        value.get("id") != registry_id
        or value.get("model_id") != model_id
        or value.get("version") != version
        or value.get("artifact_storage_id") != storage_id
        or value.get("provider_id") != "fieldora-offline"
        or value.get("network") != "offline"
        or value.get("verification") != "sha256-per-file"
    ):
        return None
    artifact_files = value.get("artifact_files")
    formats: set[str] = set()
    if isinstance(artifact_files, list):
        for item in artifact_files[:10000]:
            if not isinstance(item, dict):
                continue
            suffix = Path(str(item.get("path") or "")).suffix.lower()
            if suffix in _ALLOWED_FORMATS:
                formats.add(suffix.removeprefix("."))
    try:
        total_bytes = max(0, int(value.get("artifact_total_bytes", 0)))
    except (TypeError, ValueError):
        return None
    return {
        "id": registry_id,
        "model_id": model_id,
        "name": str(value.get("name") or model_id),
        "version": version,
        "project_id": "platform",
        "provider_id": "fieldora-offline",
        "network": "offline",
        "status": "installed",
        "artifact_storage_id": storage_id,
        "artifact_total_bytes": total_bytes,
        "source": str(value.get("source") or "offline-bundle"),
        "license_id": str(value.get("license_id") or "unspecified"),
        "verification": "sha256-per-file",
        "formats": sorted(formats),
    }


class InstalledModelApiMixin:
    """Expose installed model receipts through authenticated, PBAC-filtered metadata."""

    _installed_model_store: InstalledModelStore | None = None

    @classmethod
    def configure_model_store(cls, root: Path | None) -> None:
        cls._installed_model_store = None if root is None else InstalledModelStore(root)

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        if urlsplit(target).path == "/api/v1/ai-models/installed" and method == "GET":
            return self._installed_models(headers)
        return super().dispatch(method, target, headers, body)  # type: ignore[misc]

    def _installed_models(self, headers: dict[str, str]) -> ApiResponse:
        store = type(self)._installed_model_store
        if store is None:
            return ApiResponse.json(503, {"error": "offline_model_store_unavailable"})
        try:
            _token, identity = self._identity(headers)  # type: ignore[attr-defined]
        except AuthenticationFailed as exc:
            return ApiResponse.json(401, {"error": "unauthorized", "detail": str(exc)})
        purpose = headers.get("x-fieldora-purpose", "administration")
        disclosed = []
        for record in store.records():
            decision = self._decisions.decide(  # type: ignore[attr-defined]
                AccessRequest(
                    subject_id=identity.identity_id,
                    action="view",
                    resource_type="ai_model",
                    resource_id=str(record["id"]),
                    organization_id=identity.organization_id,
                    project_id="platform",
                    purpose=purpose,
                )
            )
            if decision.allowed:
                disclosed.append(record)
        return ApiResponse.json(200, {"items": disclosed, "count": len(disclosed)})
