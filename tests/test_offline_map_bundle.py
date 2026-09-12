from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from natureai_next.bootstrap.map_bundle_cli import (
    MapBundleError,
    install_map_bundle,
    verify_map_bundle,
)
from natureai_next.server.offline_map_store_api import InstalledMapStore


def _bundle(root: Path, *, filename: str = "region.pmtiles", payload: bytes = b"map") -> Path:
    root.mkdir()
    (root / filename).write_bytes(payload)
    manifest = {
        "package_class": "map",
        "map_id": "nl-basemap",
        "version": "2026.08",
        "source": "fieldora-bastion",
        "license_id": "ODbL-1.0",
        "files": [
            {
                "path": filename,
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        ],
        "artifact_total_bytes": len(payload),
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return root


def test_offline_map_bundle_installs_atomically_and_discovery_hides_paths(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "bundle")
    verified, destination = install_map_bundle(bundle, tmp_path / "maps")
    assert verified.artifact_storage_id == "map:nl-basemap:2026.08"
    assert (destination / "region.pmtiles").read_bytes() == b"map"
    records = InstalledMapStore(tmp_path / "maps").records()
    assert len(records) == 1
    assert records[0]["artifact_storage_id"] == "map:nl-basemap:2026.08"
    assert records[0]["formats"] == ["pmtiles"]
    assert str(tmp_path) not in json.dumps(records)


def test_offline_map_bundle_rejects_executable_content(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "bundle", filename="install.py", payload=b"print('no')")
    with pytest.raises(MapBundleError, match="unsupported or executable"):
        verify_map_bundle(bundle)


def test_offline_map_bundle_requires_map_package_class(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "bundle")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["package_class"] = "model"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(MapBundleError, match="package_class must be map"):
        verify_map_bundle(bundle)


def test_offline_map_bundle_rejects_traversal(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path / "bundle")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "../region.pmtiles"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(MapBundleError, match="unsafe bundle path"):
        verify_map_bundle(bundle)
