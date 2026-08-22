"""Cryptographic verification for packaged map-renderer assets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from natureai_next.domain.maps import RendererAssetReadiness


class Sha256RendererAssetVerifier:
    MANIFEST_NAME = "renderer-assets.json"
    REQUIRED_FILES = frozenset({"maplibre-gl.js", "maplibre-gl.css"})

    def verify(self, asset_root: Path) -> RendererAssetReadiness:
        manifest_path = asset_root / self.MANIFEST_NAME
        if not manifest_path.is_file():
            return RendererAssetReadiness(
                False,
                "renderer_assets_missing",
                "approved renderer asset manifest is not installed",
            )
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != 1 or payload.get("approval_status") != "approved":
                raise ValueError("manifest is not an approved schema version")
            entries = payload.get("assets")
            if not isinstance(entries, list):
                raise ValueError("asset list is missing")
            by_name = {entry["filename"]: entry for entry in entries if isinstance(entry, dict)}
            if set(by_name) != self.REQUIRED_FILES:
                raise ValueError("manifest must contain exactly the required renderer assets")
            for name in sorted(self.REQUIRED_FILES):
                entry = by_name[name]
                version = str(entry.get("version", "")).strip()
                license_id = str(entry.get("license", "")).strip()
                expected = str(entry.get("sha256", "")).lower()
                if not version or not license_id or len(expected) != 64:
                    raise ValueError(f"metadata is incomplete for {name}")
                path = asset_root / name
                if not path.is_file():
                    raise ValueError(f"approved asset is missing: {name}")
                observed = hashlib.sha256(path.read_bytes()).hexdigest()
                if observed != expected:
                    raise ValueError(f"checksum mismatch for {name}")
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            return RendererAssetReadiness(False, "renderer_assets_invalid", str(exc))
        return RendererAssetReadiness(
            True, "renderer_assets_verified", "approved renderer assets passed SHA-256 verification"
        )
