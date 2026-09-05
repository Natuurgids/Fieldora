"""PBAC-governed discovery of installed offline map packages."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessRequest
from natureai_next.server.api import ApiResponse

_RECEIPT_NAME = "FIELDORA-INSTALL.json"
_MAX_RECEIPT_BYTES = 1_048_576
_MAX_MAPS = 500
_ALLOWED_FORMATS = {"mbtiles", "pmtiles", "gpkg", "pbf"}


class InstalledMapStore:
    """Read bounded browser-safe receipts without exposing server filesystem paths."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def records(self) -> tuple[dict[str, object], ...]:
        if not self._root.is_dir() or self._root.is_symlink():
            return ()
        records: list[dict[str, object]] = []
        for map_dir in sorted(self._root.iterdir(), key=lambda path: path.name):
            if len(records) >= _MAX_MAPS:
                break
            if map_dir.is_symlink() or not map_dir.is_dir():
                continue
            for version_dir in sorted(map_dir.iterdir(), key=lambda path: path.name):
                if len(records) >= _MAX_MAPS:
                    break
                if version_dir.is_symlink() or not version_dir.is_dir():
                    continue
                record = _read_receipt(version_dir / _RECEIPT_NAME, map_dir.name, version_dir.name)
                if record is not None:
                    records.append(record)
        return tuple(records)


def _read_receipt(path: Path, map_id: str, version: str) -> dict[str, object] | None:
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
    if (
        value.get("id") != f"{map_id}@{version}"
        or value.get("map_id") != map_id
        or value.get("version") != version
        or value.get("artifact_storage_id") != f"map:{map_id}:{version}"
        or value.get("network") != "offline"
        or value.get("verification") != "sha256-per-file"
    ):
        return None
    formats = value.get("formats")
    if not isinstance(formats, list):
        return None
    safe_formats = sorted({str(item) for item in formats if str(item) in _ALLOWED_FORMATS})
    if not safe_formats:
        return None
    try:
        total_bytes = max(0, int(value.get("artifact_total_bytes", 0)))
    except (TypeError, ValueError):
        return None
    signature = str(value.get("manifest_signature") or "unsigned")
    if signature not in {"unsigned", "ed25519"}:
        return None
    key_id = str(value.get("signing_key_id") or "").strip()
    if signature == "ed25519" and not key_id:
        return None
    record: dict[str, object] = {
        "id": f"{map_id}@{version}",
        "map_id": map_id,
        "name": str(value.get("name") or map_id),
        "version": version,
        "network": "offline",
        "status": "installed",
        "artifact_storage_id": f"map:{map_id}:{version}",
        "artifact_total_bytes": total_bytes,
        "source": str(value.get("source") or "offline-bundle")[:2048],
        "license_id": str(value.get("license_id") or "unspecified")[:2048],
        "verification": "sha256-per-file",
        "manifest_signature": signature,
        "signing_key_id": key_id[:128],
        "formats": safe_formats,
    }
    scan = value.get("malware_scan")
    if isinstance(scan, dict) and scan.get("result") == "clean" and signature == "ed25519":
        record["malware_scan"] = {
            "result": "clean",
            "scanner": str(scan.get("scanner") or "")[:2048],
            "scanner_version": str(scan.get("scanner_version") or "")[:2048],
            "definitions": str(scan.get("definitions") or "")[:2048],
            "scanned_at": str(scan.get("scanned_at") or "")[:2048],
        }
    return record


class InstalledMapApiMixin:
    """Expose installed map receipts through the existing infrastructure PBAC vocabulary."""

    _installed_map_store: InstalledMapStore | None = None

    @classmethod
    def configure_map_store(cls, root: Path | None) -> None:
        cls._installed_map_store = None if root is None else InstalledMapStore(root)

    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes) -> ApiResponse:
        if urlsplit(target).path == "/api/v1/maps/installed" and method == "GET":
            return self._installed_maps(headers)
        return super().dispatch(method, target, headers, body)  # type: ignore[misc]

    def _installed_maps(self, headers: dict[str, str]) -> ApiResponse:
        store = type(self)._installed_map_store
        if store is None:
            root = os.environ.get("FIELDORA_MAP_STORE", "").strip()
            if not root:
                return ApiResponse.json(503, {"error": "offline_map_store_unavailable"})
            store = InstalledMapStore(Path(root))
        try:
            _token, identity = self._identity(headers)  # type: ignore[attr-defined]
        except AuthenticationFailed as exc:
            return ApiResponse.json(401, {"error": "unauthorized", "detail": str(exc)})
        decision = self._decisions.decide(  # type: ignore[attr-defined]
            AccessRequest(
                identity.identity_id,
                "infrastructure.view",
                "infrastructure",
                "offline-maps",
                identity.organization_id,
                "platform",
                headers.get("x-fieldora-purpose", "administration"),
            )
        )
        if not decision.allowed:
            return ApiResponse.json(403, {"error": "forbidden"})
        records = list(store.records())
        return ApiResponse.json(200, {"items": records, "count": len(records)})
