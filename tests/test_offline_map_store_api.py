from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from natureai_next.domain.access_control import Identity, IdentityKind
from natureai_next.server.offline_map_store_api import InstalledMapApiMixin, InstalledMapStore


def _store(root: Path) -> InstalledMapStore:
    version = root / "basemap" / "1"
    version.mkdir(parents=True)
    receipt = {
        "id": "basemap@1",
        "map_id": "basemap",
        "name": "Basemap",
        "version": "1",
        "network": "offline",
        "status": "installed",
        "artifact_storage_id": "map:basemap:1",
        "artifact_total_bytes": 123,
        "artifact_files": [{"path": "region.pmtiles", "sha256": "a" * 64, "size_bytes": 123}],
        "source": "fieldora-bastion",
        "license_id": "ODbL-1.0",
        "verification": "sha256-per-file",
        "manifest_signature": "unsigned",
        "signing_key_id": "",
        "formats": ["pmtiles"],
    }
    (version / "FIELDORA-INSTALL.json").write_text(json.dumps(receipt), encoding="utf-8")
    return InstalledMapStore(root)


class _Decisions:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return SimpleNamespace(allowed=self.allowed)


class _MapApi(InstalledMapApiMixin):
    def __init__(self, store: InstalledMapStore, *, allowed: bool) -> None:
        type(self)._installed_map_store = store
        self._decisions = _Decisions(allowed)

    def _identity(self, _headers):
        return "token", Identity("user-1", IdentityKind.USER, "User", "org-1")


def test_installed_map_api_uses_real_infrastructure_pbac_vocabulary(tmp_path: Path) -> None:
    api = _MapApi(_store(tmp_path / "maps"), allowed=True)
    response = api._installed_maps({"x-fieldora-purpose": "administration"})
    assert response.status == 200
    request = api._decisions.requests[0]
    assert request.action == "infrastructure.view"
    assert request.resource_type == "infrastructure"
    assert request.resource_id == "offline-maps"
    assert request.project_id == "platform"


def test_installed_map_api_denies_all_metadata_without_authority(tmp_path: Path) -> None:
    api = _MapApi(_store(tmp_path / "maps"), allowed=False)
    response = api._installed_maps({"x-fieldora-purpose": "administration"})
    assert response.status == 403
    assert json.loads(response.body) == {"error": "forbidden"}
    assert b"basemap" not in response.body
