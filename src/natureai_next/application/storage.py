"""Flexible storage management for Build 28.

This service deliberately works against the catalog database rather than the UI so
imports, health checks, backup, CLI tooling and the desktop share one storage model.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from natureai_next.domain.storage import AssetStoragePolicy, StorageHealth, StorageProviderKind
from natureai_next.infrastructure.storage_devices import DeviceRegistry, identify_path, mounted_volumes, resolve_device_path


@dataclass(frozen=True, slots=True)
class StorageStatistics:
    assets: int
    managed_assets: int
    referenced_assets: int
    hybrid_assets: int
    available_locations: int
    unavailable_locations: int
    managed_bytes: int


@dataclass(frozen=True, slots=True)
class ManagedRemovalPreview:
    asset_ids: tuple[int, ...]
    removable_asset_ids: tuple[int, ...]
    blocked_asset_ids: tuple[int, ...]
    managed_copies: int
    reclaimable_bytes: int


@dataclass(frozen=True, slots=True)
class VerificationResult:
    location_id: int
    asset_public_id: str
    path: str
    previous_health: str
    health: str
    detail: str | None = None


class AssetStorageService:
    def __init__(self, database_path: Path, managed_root: Path | None = None) -> None:
        self.database_path = Path(database_path)
        self.managed_root = Path(managed_root or self.database_path.parent / "managed" / "originals")
        self.device_registry = DeviceRegistry(self.database_path.parent / "storage_devices.db")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def resolve_original(self, asset_id: int) -> Path | None:
        """Return any currently usable original without changing initial provenance.

        Managed copies are preferred, then an explicitly primary source, then the
        immutable initial observation, then follow-ups in discovery order. Device
        registry resolution allows the same source to survive drive-letter changes.
        """
        with self._connect() as c:
            rows = c.execute(
                "SELECT * FROM asset_storage_locations WHERE asset_id=? "
                "ORDER BY CASE provenance_role WHEN 'managed_copy' THEN 0 WHEN 'initial' THEN 2 ELSE 3 END, "
                "is_primary DESC, discovered_at_us, id",
                (asset_id,),
            ).fetchall()
        for row in rows:
            candidate = None
            if row['device_public_id'] and row['relative_path'] is not None:
                candidate = self.device_registry.resolve(row['device_public_id'], row['relative_path'])
            if candidate is None and row['normalized_path']:
                candidate = Path(row['normalized_path'])
            if candidate is not None and candidate.is_file():
                return candidate
        return None

    def ensure_default_providers(self) -> tuple[int, int]:
        now = time.time_ns() // 1000
        with self._connect() as c:
            managed = self._provider(c, StorageProviderKind.APERTURE_LIBRARY, "Aperture Library", self.managed_root)
            local = self._provider(c, StorageProviderKind.LOCAL_FILESYSTEM, "Local filesystem", None)
            c.commit()
            return managed, local

    def _provider(self, c: sqlite3.Connection, kind: StorageProviderKind, name: str, root: Path | None, *, volume_identity: str | None = None) -> int:
        if volume_identity:
            row = c.execute("SELECT id FROM storage_providers WHERE volume_identity=?", (volume_identity,)).fetchone()
        else:
            row = c.execute("SELECT id FROM storage_providers WHERE kind=? AND display_name=?", (kind.value, name)).fetchone()
        if row:
            return int(row["id"])
        now = time.time_ns() // 1000
        return int(c.execute(
            "INSERT INTO storage_providers(public_id,kind,display_name,root_uri,volume_identity,configuration_json,created_at_us,modified_at_us) VALUES(?,?,?,?,?, '{}',?,?)",
            (str(uuid.uuid4()), kind.value, name, str(root) if root else None, volume_identity, now, now),
        ).lastrowid)

    def register_import(self, *, asset_id: int, policy: AssetStoragePolicy, source_path: Path,
                        source_file_instance_id: int | None, managed_path: Path | None,
                        managed_file_instance_id: int | None, file_size: int, modified_at_us: int | None,
                        sha256: str, fast_fingerprint: str | None = None) -> None:
        managed_provider, local_provider = self.ensure_default_providers()
        source_device = identify_path(source_path)
        with self._connect() as provider_connection:
            source_provider = self._provider(
                provider_connection, StorageProviderKind.REMOVABLE_VOLUME,
                source_device.label or "Storage device", source_device.mount_path,
                volume_identity=source_device.identity,
            )
            provider_connection.commit()
        now = time.time_ns() // 1000
        with self._connect() as c:
            c.execute(
                "INSERT INTO asset_storage_policies(asset_id,policy,created_at_us,modified_at_us) VALUES(?,?,?,?) "
                "ON CONFLICT(asset_id) DO UPDATE SET policy=excluded.policy,modified_at_us=excluded.modified_at_us",
                (asset_id, policy.value, now, now),
            )
            if policy in {AssetStoragePolicy.REFERENCED, AssetStoragePolicy.HYBRID}:
                self._upsert_location(c, asset_id=asset_id, provider_id=source_provider,
                    file_instance_id=source_file_instance_id, role="source", path=source_path,
                    file_size=file_size, modified_at_us=modified_at_us, sha256=sha256,
                    fast_fingerprint=fast_fingerprint, primary=policy is AssetStoragePolicy.REFERENCED, now=now)
            if managed_path is not None and policy in {AssetStoragePolicy.MANAGED, AssetStoragePolicy.HYBRID}:
                self._upsert_location(c, asset_id=asset_id, provider_id=managed_provider,
                    file_instance_id=managed_file_instance_id, role="aperture_master", path=managed_path,
                    file_size=file_size, modified_at_us=modified_at_us, sha256=sha256,
                    fast_fingerprint=fast_fingerprint, primary=True, now=now)
            c.commit()

    def _upsert_location(self, c: sqlite3.Connection, *, asset_id: int, provider_id: int,
                         file_instance_id: int | None, role: str, path: Path, file_size: int,
                         modified_at_us: int | None, sha256: str, fast_fingerprint: str | None,
                         primary: bool, now: int) -> None:
        normalized = os.path.normpath(str(path.expanduser().resolve(strict=False)))
        path_key = os.path.normcase(normalized).casefold()
        device = identify_path(path) if role == "source" else None
        registered = self.device_registry.register_path(path) if role == "source" else None
        c.execute(
            "INSERT INTO asset_storage_locations(public_id,asset_id,provider_id,file_instance_id,role,normalized_path,path_key,source_uri,file_size,modified_at_observed_us,sha256,fast_fingerprint,health,is_primary,last_verified_at_us,created_at_us,modified_at_us,device_identity,volume_label,relative_path,last_mount_path,device_public_id,location_public_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(asset_id,role,path_key) DO UPDATE SET file_instance_id=excluded.file_instance_id,file_size=excluded.file_size,modified_at_observed_us=excluded.modified_at_observed_us,sha256=excluded.sha256,fast_fingerprint=excluded.fast_fingerprint,health='available',is_primary=excluded.is_primary,last_verified_at_us=excluded.last_verified_at_us,modified_at_us=excluded.modified_at_us",
            (str(uuid.uuid4()), asset_id, provider_id, file_instance_id, role, normalized, path_key,
             Path(normalized).as_uri(), file_size, modified_at_us, sha256, fast_fingerprint,
             StorageHealth.AVAILABLE.value, 1 if primary else 0, now, now, now,
             device.identity if device else None, device.label if device else None,
             device.relative_path if device else None, str(device.mount_path) if device else None,
             registered.device_public_id if registered else None, registered.location_public_id if registered else None),
        )

    def statistics(self) -> StorageStatistics:
        with self._connect() as c:
            policy = {r["policy"]: r["n"] for r in c.execute("SELECT policy,COUNT(*) n FROM asset_storage_policies GROUP BY policy")}
            assets = c.execute("SELECT COUNT(*) FROM assets WHERE lifecycle_state!='purged'").fetchone()[0]
            available = c.execute("SELECT COUNT(*) FROM asset_storage_locations WHERE health='available'").fetchone()[0]
            unavailable = c.execute("SELECT COUNT(*) FROM asset_storage_locations WHERE health!='available'").fetchone()[0]
            managed_bytes = c.execute("SELECT COALESCE(SUM(file_size),0) FROM asset_storage_locations WHERE role='aperture_master'").fetchone()[0]
        return StorageStatistics(int(assets), int(policy.get('managed',0)), int(policy.get('referenced',0)),
                                 int(policy.get('hybrid',0)), int(available), int(unavailable), int(managed_bytes))

    def list_locations(self, *, health: str | None = None) -> list[sqlite3.Row]:
        # Reconcile only the small device registry. No per-item filesystem probes
        # occur while rendering thousands of catalog rows.
        self.device_registry.reconcile()
        device_states = {str(row["public_id"]): str(row["status"]) for row in self.device_registry.list_devices()}
        sql = "SELECT l.*,a.public_id asset_public_id,p.policy,sp.display_name provider_name FROM asset_storage_locations l JOIN assets a ON a.id=l.asset_id LEFT JOIN asset_storage_policies p ON p.asset_id=a.id JOIN storage_providers sp ON sp.id=l.provider_id"
        sql += " ORDER BY CASE WHEN l.health='available' THEN 1 ELSE 0 END,l.modified_at_us DESC"
        with self._connect() as c:
            rows = list(c.execute(sql))
        enriched: list[sqlite3.Row] = []
        # sqlite.Row cannot be extended; return lightweight dictionaries, which
        # preserve the mapping API used by the UI and tests.
        for row in rows:
            item = dict(row)
            device_state = device_states.get(str(item.get("device_public_id")), "unknown")
            effective = "offline" if item.get("role") == "source" and device_state == "offline" else item["health"]
            item["device_status"] = device_state
            item["effective_health"] = effective
            item["health"] = effective
            if health is None or effective == health:
                enriched.append(item)  # type: ignore[arg-type]
        return enriched

    def verify(
        self,
        location_ids: list[int] | None = None,
        *,
        full_hash: bool = False,
        progress=None,
        cancelled=None,
        commit_batch_size: int = 50,
    ) -> list[VerificationResult]:
        now = time.time_ns() // 1000
        results: list[VerificationResult] = []
        self.device_registry.reconcile()
        with self._connect() as c:
            sql = "SELECT l.*,a.public_id asset_public_id FROM asset_storage_locations l JOIN assets a ON a.id=l.asset_id"
            params: tuple[object,...] = ()
            if location_ids:
                marks=','.join('?' for _ in location_ids); sql += f" WHERE l.id IN ({marks})"; params=tuple(location_ids)
            rows = c.execute(sql, params).fetchall()
            total = len(rows)
            if progress is not None:
                progress(0, total, "Preparing storage verification")
            for index, row in enumerate(rows, start=1):
                if cancelled is not None and cancelled():
                    c.commit()
                    raise InterruptedError("Storage verification cancelled")
                path=Path(row['normalized_path']); previous=row['health']; detail=None
                if row['role'] == 'source' and row['relative_path']:
                    resolved = self.device_registry.resolve(row['device_public_id'], row['relative_path'])
                    if resolved is None and row['device_identity']:
                        resolved = resolve_device_path(row['device_identity'], row['relative_path'])
                    if resolved is not None:
                        path = resolved
                        normalized = os.path.normpath(str(path.resolve(strict=False)))
                        path_key = os.path.normcase(normalized).casefold()
                        mount = mounted_volumes().get(row['device_identity'])
                        c.execute(
                            "UPDATE asset_storage_locations SET normalized_path=?,path_key=?,source_uri=?,last_mount_path=?,modified_at_us=? WHERE id=?",
                            (normalized, path_key, path.resolve(strict=False).as_uri(), str(mount.mount_path) if mount else row['last_mount_path'], now, row['id']),
                        )
                try:
                    stat=path.stat()
                    health=StorageHealth.AVAILABLE.value
                    if row['file_size'] is not None and stat.st_size != row['file_size']:
                        health=StorageHealth.CHANGED.value; detail="File size changed"
                    digest=None
                    if full_hash and health == StorageHealth.AVAILABLE.value and row['sha256']:
                        digest=self._sha256(path)
                        if digest != row['sha256']:
                            health=StorageHealth.CHANGED.value; detail="Checksum changed"
                    c.execute("UPDATE asset_storage_locations SET health=?,last_verified_at_us=?,modified_at_us=? WHERE id=?", (health,now,now,row['id']))
                    c.execute("INSERT INTO storage_verification_events(public_id,storage_location_id,previous_health,observed_health,observed_size,observed_modified_at_us,observed_sha256,detail,verified_at_us) VALUES(?,?,?,?,?,?,?,?,?)",
                              (str(uuid.uuid4()),row['id'],previous,health,stat.st_size,stat.st_mtime_ns//1000,digest,detail,now))
                except FileNotFoundError:
                    registry_offline = row['role'] == 'source' and self.device_registry.device_status(row['device_public_id']) == 'offline'
                    if registry_offline or (row['role'] == 'source' and row['device_identity'] and row['device_identity'] not in mounted_volumes()):
                        health=StorageHealth.OFFLINE.value; detail="Storage device is offline"
                    else:
                        health=StorageHealth.MISSING.value; detail="Path not found on the connected device"
                    c.execute("UPDATE asset_storage_locations SET health=?,last_verified_at_us=?,modified_at_us=? WHERE id=?", (health,now,now,row['id']))
                except PermissionError:
                    health=StorageHealth.PERMISSION_DENIED.value; detail="Permission denied"
                    c.execute("UPDATE asset_storage_locations SET health=?,last_verified_at_us=?,modified_at_us=? WHERE id=?", (health,now,now,row['id']))
                if row['file_instance_id']:
                    c.execute(
                        "UPDATE file_instances SET availability_state=?,verified_at_us=?,modified_at_us=? WHERE id=?",
                        (_catalog_availability(health), now, now, row['file_instance_id']),
                    )
                results.append(VerificationResult(row['id'],row['asset_public_id'],str(path),previous,health,detail))
                if index % max(1, commit_batch_size) == 0:
                    c.commit()
                if progress is not None:
                    progress(index, total, f"Verified {index:,} of {total:,} storage locations")
            affected = {r.asset_public_id for r in results}
            for public_id in affected:
                available = c.execute(
                    "SELECT 1 FROM asset_storage_locations l JOIN assets a ON a.id=l.asset_id "
                    "WHERE a.public_id=? AND l.health='available' LIMIT 1", (public_id,),
                ).fetchone() is not None
                state = 'available' if available else 'offline'
                c.execute(
                    "UPDATE library_assets SET availability_state=?,updated_at_us=? WHERE asset_public_id=?",
                    (state, now, public_id),
                )
            c.commit()
        return results

    def relink(self, location_id: int, new_path: Path) -> None:
        path=Path(new_path).expanduser().resolve(); stat=path.stat(); now=time.time_ns()//1000
        with self._connect() as c:
            row=c.execute("SELECT sha256,file_instance_id FROM asset_storage_locations WHERE id=?",(location_id,)).fetchone()
            if row is None: raise KeyError(location_id)
            if row['sha256'] and self._sha256(path) != row['sha256']:
                raise ValueError("Selected file does not match the stored SHA-256 checksum")
            normalized=os.path.normpath(str(path)); key=os.path.normcase(normalized).casefold()
            device = identify_path(path)
            registered = self.device_registry.register_path(path)
            provider_id = self._provider(
                c, StorageProviderKind.REMOVABLE_VOLUME, device.label or "Storage device",
                device.mount_path, volume_identity=device.identity,
            )
            c.execute("UPDATE asset_storage_locations SET provider_id=?,normalized_path=?,path_key=?,source_uri=?,file_size=?,modified_at_observed_us=?,health='available',last_verified_at_us=?,modified_at_us=?,device_identity=?,volume_label=?,relative_path=?,last_mount_path=?,device_public_id=?,location_public_id=? WHERE id=?",
                      (provider_id,normalized,key,path.as_uri(),stat.st_size,stat.st_mtime_ns//1000,now,now,
                       device.identity,device.label,device.relative_path,str(device.mount_path),registered.device_public_id,registered.location_public_id,location_id))
            if row['file_instance_id']:
                c.execute("UPDATE file_instances SET normalized_path=?,path_key=?,file_size=?,modified_at_observed_us=?,availability_state='available',verified_at_us=?,modified_at_us=? WHERE id=?",
                          (normalized,key,stat.st_size,stat.st_mtime_ns//1000,now,now,row['file_instance_id']))
            c.commit()

    def create_aperture_master(self, asset_id: int) -> Path:
        """Create and register a managed original without creating a second asset.

        The managed copy becomes the primary file instance while the referenced
        source remains attached, making the asset Hybrid and immediately visible
        to every catalog query that follows ``assets.primary_file_instance_id``.
        """
        with self._connect() as c:
            source = c.execute(
                "SELECT * FROM asset_storage_locations WHERE asset_id=? AND role='source' "
                "ORDER BY is_primary DESC,id LIMIT 1", (asset_id,)
            ).fetchone()
            if source is None:
                raise ValueError("Asset has no source location")
            src = Path(source['normalized_path'])
            if not src.is_file():
                raise FileNotFoundError(src)
            digest = source['sha256'] or self._sha256(src)
            destination = self.managed_root / digest[:2] / digest[2:4] / f"{digest}{src.suffix.lower()}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                temp = destination.with_suffix(destination.suffix + '.part')
                shutil.copy2(src, temp)
                if self._sha256(temp) != digest:
                    temp.unlink(missing_ok=True)
                    raise OSError("Managed copy verification failed")
                temp.replace(destination)

            now = time.time_ns() // 1000
            source_file = None
            if source['file_instance_id']:
                source_file = c.execute("SELECT * FROM file_instances WHERE id=?", (source['file_instance_id'],)).fetchone()
            existing = c.execute(
                "SELECT * FROM file_instances WHERE asset_id=? AND storage_mode='managed' AND sha256=? "
                "ORDER BY id LIMIT 1", (asset_id, digest)
            ).fetchone()
            normalized = os.path.normpath(str(destination.resolve(strict=False)))
            path_key = os.path.normcase(normalized).casefold()
            if existing is None:
                public_id = str(uuid.uuid4())
                file_id = int(c.execute(
                    "INSERT INTO file_instances(public_id,asset_id,storage_mode,role,normalized_path,path_key,file_size,modified_at_observed_us,sha256,availability_state,mime_type,format_name,fast_fingerprint,import_source_path,verified_at_us,created_at_us,modified_at_us) "
                    "VALUES(?,?,'managed','original',?,?,?,?,?,'available',?,?,?,?,?,?,?)",
                    (public_id, asset_id, normalized, path_key, destination.stat().st_size,
                     destination.stat().st_mtime_ns // 1000, digest,
                     source_file['mime_type'] if source_file else None,
                     source_file['format_name'] if source_file else src.suffix.lstrip('.').upper(),
                     source['fast_fingerprint'], str(src), now, now, now),
                ).lastrowid)
            else:
                file_id = int(existing['id'])
                public_id = str(existing['public_id'])
                c.execute(
                    "UPDATE file_instances SET role='original',normalized_path=?,path_key=?,file_size=?,modified_at_observed_us=?,availability_state='available',verified_at_us=?,modified_at_us=? WHERE id=?",
                    (normalized, path_key, destination.stat().st_size, destination.stat().st_mtime_ns // 1000, now, now, file_id),
                )

            provider, _ = self.ensure_default_providers()
            self._upsert_location(
                c, asset_id=asset_id, provider_id=provider, file_instance_id=file_id,
                role='aperture_master', path=destination, file_size=destination.stat().st_size,
                modified_at_us=destination.stat().st_mtime_ns // 1000, sha256=digest,
                fast_fingerprint=source['fast_fingerprint'], primary=True, now=now,
            )
            c.execute("UPDATE asset_storage_locations SET is_primary=0 WHERE asset_id=? AND role='source'", (asset_id,))
            c.execute("UPDATE assets SET primary_file_instance_id=?,modified_at_us=?,revision=revision+1 WHERE id=?", (file_id, now, asset_id))
            c.execute("UPDATE library_assets SET primary_file_public_id=?,availability_state='available',updated_at_us=? WHERE asset_public_id=(SELECT public_id FROM assets WHERE id=?)", (public_id, now, asset_id))
            c.execute("UPDATE image_properties SET file_instance_id=? WHERE asset_id=?", (file_id, asset_id))
            c.execute(
                "INSERT INTO asset_storage_policies(asset_id,policy,created_at_us,modified_at_us) VALUES(?, 'hybrid', ?, ?) "
                "ON CONFLICT(asset_id) DO UPDATE SET policy='hybrid',modified_at_us=excluded.modified_at_us",
                (asset_id, now, now),
            )
            c.commit()
            return destination


    def managed_removal_preview(self, asset_ids: list[int] | tuple[int, ...]) -> ManagedRemovalPreview:
        """Return a safety preview for bulk managed-copy removal."""
        unique = tuple(sorted({int(value) for value in asset_ids}))
        removable: list[int] = []
        blocked: list[int] = []
        copies = 0
        reclaimable = 0
        with self._connect() as c:
            for asset_id in unique:
                masters = c.execute(
                    "SELECT file_size FROM asset_storage_locations WHERE asset_id=? AND role='aperture_master'",
                    (asset_id,),
                ).fetchall()
                if not masters:
                    continue
                copies += len(masters)
                source = c.execute(
                    "SELECT normalized_path FROM asset_storage_locations WHERE asset_id=? AND role='source' "
                    "ORDER BY is_primary DESC,id LIMIT 1", (asset_id,),
                ).fetchone()
                if source is None or not Path(source['normalized_path']).is_file():
                    blocked.append(asset_id)
                    continue
                removable.append(asset_id)
                reclaimable += sum(int(row['file_size'] or 0) for row in masters)
        return ManagedRemovalPreview(unique, tuple(removable), tuple(blocked), copies, reclaimable)

    def assets_in_storage_scope(self, scope: Path) -> list[int]:
        """Return assets with any registered source or managed location under *scope*."""
        resolved = Path(scope).expanduser().resolve(strict=False)
        selected: set[int] = set()
        with self._connect() as c:
            for row in c.execute("SELECT asset_id,normalized_path FROM asset_storage_locations"):
                try:
                    candidate = Path(row['normalized_path']).expanduser().resolve(strict=False)
                    candidate.relative_to(resolved)
                except (OSError, ValueError):
                    continue
                selected.add(int(row['asset_id']))
        return sorted(selected)

    def remove_aperture_masters(self, asset_ids: list[int] | tuple[int, ...], *, delete_file: bool = True) -> ManagedRemovalPreview:
        """Remove all safe managed copies in *asset_ids* and return the preflight used."""
        preview = self.managed_removal_preview(asset_ids)
        for asset_id in preview.removable_asset_ids:
            self.remove_aperture_master(asset_id, delete_file=delete_file)
        return preview

    def remove_aperture_master(self, asset_id: int, *, delete_file: bool = True) -> None:
        """Remove only Aperture's managed copy and keep the asset referenced.

        This operation never trashes the catalog asset.  It first promotes the
        referenced source to a real primary file instance, then removes managed
        file-instance and storage-location records, and finally deletes the copy.
        """
        paths_to_delete: list[Path] = []
        with self._connect() as c:
            source = c.execute(
                "SELECT * FROM asset_storage_locations WHERE asset_id=? AND role='source' "
                "ORDER BY is_primary DESC,id LIMIT 1", (asset_id,)
            ).fetchone()
            if source is None:
                raise ValueError("Cannot remove the only original; relink a source first")
            src = Path(source['normalized_path'])
            if not src.is_file():
                raise FileNotFoundError("Linked source is unavailable; locate it before removing the managed copy")
            now = time.time_ns() // 1000
            source_file = None
            if source['file_instance_id']:
                source_file = c.execute("SELECT * FROM file_instances WHERE id=?", (source['file_instance_id'],)).fetchone()
            if source_file is None:
                managed = c.execute(
                    "SELECT * FROM file_instances WHERE asset_id=? AND storage_mode='managed' ORDER BY id LIMIT 1", (asset_id,)
                ).fetchone()
                normalized = os.path.normpath(str(src.resolve(strict=False)))
                path_key = os.path.normcase(normalized).casefold()
                public_id = str(uuid.uuid4())
                source_file_id = int(c.execute(
                    "INSERT INTO file_instances(public_id,asset_id,storage_mode,role,normalized_path,path_key,file_size,modified_at_observed_us,sha256,availability_state,mime_type,format_name,fast_fingerprint,import_source_path,verified_at_us,created_at_us,modified_at_us) "
                    "VALUES(?,?,'referenced','original',?,?,?,?,?,'available',?,?,?,?,?,?,?)",
                    (public_id, asset_id, normalized, path_key, src.stat().st_size,
                     src.stat().st_mtime_ns // 1000, source['sha256'] or self._sha256(src),
                     managed['mime_type'] if managed else None,
                     managed['format_name'] if managed else src.suffix.lstrip('.').upper(),
                     source['fast_fingerprint'], str(src), now, now, now),
                ).lastrowid)
                c.execute("UPDATE asset_storage_locations SET file_instance_id=? WHERE id=?", (source_file_id, source['id']))
            else:
                source_file_id = int(source_file['id'])
                public_id = str(source_file['public_id'])
                c.execute("UPDATE file_instances SET role='original',storage_mode='referenced',availability_state='available',modified_at_us=? WHERE id=?", (now, source_file_id))

            masters = c.execute(
                "SELECT id,file_instance_id,normalized_path FROM asset_storage_locations WHERE asset_id=? AND role='aperture_master'", (asset_id,)
            ).fetchall()
            managed_ids = {int(row['file_instance_id']) for row in masters if row['file_instance_id']}
            managed_ids.update(int(r[0]) for r in c.execute("SELECT id FROM file_instances WHERE asset_id=? AND storage_mode='managed'", (asset_id,)))
            paths_to_delete = [Path(row['normalized_path']) for row in masters]

            c.execute("UPDATE asset_storage_locations SET is_primary=1,health='available',modified_at_us=? WHERE id=?", (now, source['id']))
            c.execute("UPDATE assets SET primary_file_instance_id=?,lifecycle_state='active',modified_at_us=?,revision=revision+1 WHERE id=?", (source_file_id, now, asset_id))
            c.execute("UPDATE library_assets SET primary_file_public_id=?,availability_state='available',updated_at_us=? WHERE asset_public_id=(SELECT public_id FROM assets WHERE id=?)", (public_id, now, asset_id))
            c.execute("UPDATE image_properties SET file_instance_id=? WHERE asset_id=?", (source_file_id, asset_id))
            c.execute("DELETE FROM asset_storage_locations WHERE asset_id=? AND role='aperture_master'", (asset_id,))
            for file_id in managed_ids:
                # Derivatives belong to the catalog asset. Rebind their provenance
                # before deleting the managed file instance so thumbnails/previews
                # survive a Hybrid -> Referenced conversion.
                c.execute(
                    "UPDATE derivative_cache_entries SET source_file_instance_id=? WHERE source_file_instance_id=?",
                    (source_file_id, file_id),
                )
                c.execute("UPDATE metadata_snapshots SET file_instance_id=? WHERE file_instance_id=?", (source_file_id, file_id))
                # Historical import rows retain provenance but must no longer pin
                # the removable managed file instance through a NO ACTION FK.
                c.execute("UPDATE import_plan_items SET file_instance_id=? WHERE file_instance_id=?", (source_file_id, file_id))
                c.execute("DELETE FROM file_instances WHERE id=?", (file_id,))
            c.execute(
                "INSERT INTO asset_storage_policies(asset_id,policy,created_at_us,modified_at_us) VALUES(?, 'referenced', ?, ?) "
                "ON CONFLICT(asset_id) DO UPDATE SET policy='referenced',modified_at_us=excluded.modified_at_us",
                (asset_id, now, now),
            )
            c.commit()
        if delete_file:
            for path in paths_to_delete:
                path.unlink(missing_ok=True)
    @staticmethod
    def _sha256(path: Path) -> str:
        digest=hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024*1024),b''): digest.update(chunk)
        return digest.hexdigest()


def _catalog_availability(health: str) -> str:
    if health == StorageHealth.AVAILABLE.value:
        return 'available'
    if health in {StorageHealth.OFFLINE.value, StorageHealth.PERMISSION_DENIED.value}:
        return 'offline'
    return 'missing'
