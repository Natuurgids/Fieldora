"""Policy-filtered governed pack creation and isolated desktop installation."""

from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

from natureai_next.domain.governed_packs import (
    GOVERNED_PACK_FORMAT,
    GOVERNED_PACK_VERSION,
    GovernedPackSummary,
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


class GovernedPackBuilder:
    def build(
        self,
        destination: Path,
        *,
        pack_id: str,
        enrollment_id: str,
        project_id: str,
        version: int,
        base_version: int = 0,
        records: tuple[dict, ...],
        tombstones: tuple[dict, ...] = (),
        disclose,
    ) -> GovernedPackSummary:
        if version <= base_version or base_version < 0:
            raise ValueError("pack version must be newer than its base")
        disclosed = []
        for record in records:
            filtered = disclose(record)
            if filtered is not None:
                disclosed.append(filtered)
        disclosed_tombstones = []
        for tombstone in tombstones:
            filtered = disclose(tombstone)
            if filtered is not None:
                disclosed_tombstones.append(filtered)
        payload = {
            "records": disclosed,
            "tombstones": disclosed_tombstones,
        }
        payload_bytes = _canonical(payload)
        manifest = {
            "format": GOVERNED_PACK_FORMAT,
            "format_version": GOVERNED_PACK_VERSION,
            "pack_id": pack_id,
            "enrollment_id": enrollment_id,
            "project_id": project_id,
            "version": version,
            "base_version": base_version,
            "record_count": len(disclosed),
            "tombstone_count": len(disclosed_tombstones),
            "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", _canonical(manifest))
            archive.writestr("payload.json", payload_bytes)
        package_sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
        return GovernedPackSummary(
            pack_id, enrollment_id, project_id, version, base_version,
            len(disclosed), len(disclosed_tombstones), package_sha256,
        )


class GovernedPackInstaller:
    def __init__(self, pack_root: Path, registry) -> None:
        self._pack_root = pack_root
        self._registry = registry

    def install(self, source: Path) -> GovernedPackSummary:
        with zipfile.ZipFile(source) as archive:
            if set(archive.namelist()) != {"manifest.json", "payload.json"}:
                raise ValueError("governed pack contains unexpected members")
            manifest = json.loads(archive.read("manifest.json"))
            payload_bytes = archive.read("payload.json")
        if (
            manifest.get("format") != GOVERNED_PACK_FORMAT
            or manifest.get("format_version") != GOVERNED_PACK_VERSION
            or hashlib.sha256(payload_bytes).hexdigest() != manifest.get("payload_sha256")
        ):
            raise ValueError("governed pack manifest or payload is invalid")
        payload = json.loads(payload_bytes)
        if (
            len(payload.get("records", [])) != int(manifest["record_count"])
            or len(payload.get("tombstones", [])) != int(manifest["tombstone_count"])
        ):
            raise ValueError("governed pack counts do not match payload")
        current = self._registry.pack_version(str(manifest["enrollment_id"]))
        base_version = int(manifest["base_version"])
        if base_version and current != base_version:
            raise ValueError("delta pack base version does not match installed pack")
        if not base_version and current:
            raise ValueError("full pack would overwrite an installed governed pack")
        target = self._pack_root / str(manifest["enrollment_id"]) / "payload.json"
        if base_version:
            installed = json.loads(target.read_bytes())
            records_by_id = {
                str(record["id"]): record for record in installed.get("records", [])
            }
            for tombstone in payload["tombstones"]:
                records_by_id.pop(str(tombstone["id"]), None)
            for record in payload["records"]:
                records_by_id[str(record["id"])] = record
            payload = {
                "records": [records_by_id[key] for key in sorted(records_by_id)],
                "tombstones": payload["tombstones"],
            }
            payload_bytes = _canonical(payload)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_suffix(".pending")
        with staging.open("wb") as stream:
            stream.write(payload_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, target)
        self._registry.put_pack(
            str(manifest["pack_id"]), str(manifest["enrollment_id"]),
            str(manifest["project_id"]), int(manifest["version"]),
            str(target), hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        return GovernedPackSummary(
            str(manifest["pack_id"]), str(manifest["enrollment_id"]),
            str(manifest["project_id"]), int(manifest["version"]), base_version,
            int(manifest["record_count"]), int(manifest["tombstone_count"]),
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )
