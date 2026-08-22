"""Persistent storage-device identity and mount resolution.

Drive letters and mount paths are access points, not identities.  Linked originals
are identified by a volume UUID (or the strongest platform fallback available)
plus a path relative to that volume.
"""
from __future__ import annotations

import os
import sys
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MountedVolume:
    identity: str
    label: str | None
    mount_path: Path


@dataclass(frozen=True, slots=True)
class DevicePath:
    identity: str
    label: str | None
    mount_path: Path
    relative_path: str

    def resolve(self, mount_path: Path | None = None) -> Path:
        return Path(mount_path or self.mount_path) / Path(self.relative_path)


def _normal(value: Path) -> Path:
    return Path(os.path.normpath(str(value.expanduser().resolve(strict=False))))


def identify_path(path: Path) -> DevicePath:
    """Return the persistent volume identity and relative path for *path*.

    On Windows the Volume GUID is used.  On POSIX, a filesystem UUID is used
    when exposed through /dev/disk/by-uuid; otherwise the device number is a
    deterministic local fallback.
    """
    path = _normal(path)
    if os.name == "nt":
        return _identify_windows(path)
    return _identify_posix(path)


def mounted_volumes() -> dict[str, MountedVolume]:
    volumes = _mounted_windows() if os.name == "nt" else _mounted_posix()
    return {volume.identity: volume for volume in volumes}


def resolve_device_path(identity: str | None, relative_path: str | None) -> Path | None:
    if not identity or relative_path is None:
        return None
    volume = mounted_volumes().get(identity)
    return volume.mount_path / Path(relative_path) if volume else None


def _identify_windows(path: Path) -> DevicePath:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    volume_path = ctypes.create_unicode_buffer(32768)
    if not kernel32.GetVolumePathNameW(str(path), volume_path, len(volume_path)):
        raise OSError(ctypes.get_last_error(), "GetVolumePathNameW failed", str(path))
    mount = Path(volume_path.value)

    guid = ctypes.create_unicode_buffer(32768)
    identity: str | None = None
    if kernel32.GetVolumeNameForVolumeMountPointW(str(mount), guid, len(guid)):
        identity = guid.value.rstrip("\\").casefold()

    label = ctypes.create_unicode_buffer(261)
    fs_name = ctypes.create_unicode_buffer(261)
    serial = wintypes.DWORD()
    max_component = wintypes.DWORD()
    flags = wintypes.DWORD()
    if kernel32.GetVolumeInformationW(
        str(mount), label, len(label), ctypes.byref(serial), ctypes.byref(max_component),
        ctypes.byref(flags), fs_name, len(fs_name),
    ):
        fallback = f"windows-volume-serial:{serial.value:08x}"
        identity = identity or fallback
        volume_label = label.value or None
    else:
        volume_label = None
        identity = identity or f"windows-mount:{str(mount).casefold()}"

    relative = os.path.relpath(str(path), str(mount))
    return DevicePath(identity, volume_label, mount, relative)


def _mounted_windows() -> list[MountedVolume]:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    size = kernel32.GetLogicalDriveStringsW(0, None)
    buffer = ctypes.create_unicode_buffer(size + 1)
    kernel32.GetLogicalDriveStringsW(size, buffer)
    drives = [value for value in buffer[:size].split("\0") if value]
    result: list[MountedVolume] = []
    for drive in drives:
        try:
            info = _identify_windows(Path(drive))
        except OSError:
            continue
        result.append(MountedVolume(info.identity, info.label, info.mount_path))
    return result


def _mount_rows() -> list[tuple[Path, str]]:
    rows: list[tuple[Path, str]] = []
    mountinfo = Path("/proc/self/mountinfo")
    if mountinfo.is_file():
        for line in mountinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            before, sep, after = line.partition(" - ")
            if not sep:
                continue
            left = before.split()
            right = after.split()
            if len(left) >= 5 and len(right) >= 2:
                mount = Path(left[4].replace("\\040", " "))
                source = right[1].replace("\\040", " ")
                rows.append((mount, source))
    if not rows:
        rows.append((Path("/"), ""))
    return rows


def _uuid_for_source(source: str) -> str | None:
    if not source.startswith("/dev/"):
        return None
    try:
        source_stat = os.stat(source)
    except OSError:
        return None
    uuid_dir = Path("/dev/disk/by-uuid")
    if not uuid_dir.is_dir():
        return None
    for entry in uuid_dir.iterdir():
        try:
            if os.stat(entry).st_rdev == source_stat.st_rdev:
                return entry.name
        except OSError:
            continue
    return None


def _identify_posix(path: Path) -> DevicePath:
    candidates = []
    for mount, source in _mount_rows():
        try:
            path.relative_to(mount)
        except ValueError:
            continue
        candidates.append((len(mount.parts), mount, source))
    _length, mount, source = max(candidates, default=(1, Path(path.anchor or "/"), ""))
    fs_uuid = _uuid_for_source(source)
    try:
        device_number = os.stat(mount).st_dev
    except OSError:
        device_number = os.stat(path.parent if path.parent.exists() else Path("/")).st_dev
    identity = f"filesystem-uuid:{fs_uuid}" if fs_uuid else f"posix-device:{device_number}"
    relative = str(path.relative_to(mount)) if path != mount else "."
    label = Path(source).name if source.startswith("/dev/") else None
    return DevicePath(identity, label, mount, relative)


def _mounted_posix() -> list[MountedVolume]:
    result: list[MountedVolume] = []
    seen: set[str] = set()
    for mount, _source in _mount_rows():
        try:
            info = _identify_posix(mount)
        except OSError:
            continue
        if info.identity in seen:
            continue
        seen.add(info.identity)
        result.append(MountedVolume(info.identity, info.label, mount))
    return result


@dataclass(frozen=True, slots=True)
class RegisteredStorage:
    device_public_id: str
    location_public_id: str
    identity: str
    label: str | None
    mount_path: Path
    relative_path: str


class DeviceRegistry:
    """Library-wide device and location availability registry.

    One row represents a physical volume/provider regardless of how many catalog
    items refer to it. Item records retain only public IDs plus their relative
    file path. Mount/unmount reconciliation therefore updates O(devices), not
    O(items).
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS devices(
                id INTEGER PRIMARY KEY,
                public_id TEXT NOT NULL UNIQUE,
                identity TEXT NOT NULL UNIQUE,
                label TEXT,
                provider_kind TEXT NOT NULL DEFAULT 'volume',
                status TEXT NOT NULL CHECK(status IN ('online','offline','unavailable','unknown')),
                current_mount_path TEXT,
                last_mount_path TEXT,
                last_seen_at_us INTEGER,
                checked_at_us INTEGER NOT NULL,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS locations(
                id INTEGER PRIMARY KEY,
                public_id TEXT NOT NULL UNIQUE,
                device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                root_relative_path TEXT NOT NULL DEFAULT '.',
                display_name TEXT,
                status TEXT NOT NULL CHECK(status IN ('available','unavailable','unknown')),
                checked_at_us INTEGER NOT NULL,
                error TEXT,
                UNIQUE(device_id,root_relative_path)
            );
            CREATE INDEX IF NOT EXISTS ix_devices_status ON devices(status,identity);
            CREATE INDEX IF NOT EXISTS ix_locations_device ON locations(device_id,status);
            """)

    def register_path(self, path: Path) -> RegisteredStorage:
        info = identify_path(path)
        now = time.time_ns() // 1000
        with self._connect() as c:
            row = c.execute("SELECT id,public_id FROM devices WHERE identity=?", (info.identity,)).fetchone()
            if row is None:
                device_public_id = str(uuid.uuid4())
                device_id = int(c.execute(
                    "INSERT INTO devices(public_id,identity,label,status,current_mount_path,last_mount_path,last_seen_at_us,checked_at_us) VALUES(?,?,?,'online',?,?,?,?)",
                    (device_public_id, info.identity, info.label, str(info.mount_path), str(info.mount_path), now, now),
                ).lastrowid)
            else:
                device_id = int(row['id']); device_public_id = str(row['public_id'])
                c.execute(
                    "UPDATE devices SET label=COALESCE(?,label),status='online',current_mount_path=?,last_mount_path=?,last_seen_at_us=?,checked_at_us=?,error=NULL WHERE id=?",
                    (info.label, str(info.mount_path), str(info.mount_path), now, now, device_id),
                )
            location = c.execute(
                "SELECT public_id FROM locations WHERE device_id=? AND root_relative_path='.'", (device_id,)
            ).fetchone()
            if location is None:
                location_public_id = str(uuid.uuid4())
                c.execute(
                    "INSERT INTO locations(public_id,device_id,root_relative_path,display_name,status,checked_at_us) VALUES(?,?,'.',?,'available',?)",
                    (location_public_id, device_id, info.label or 'Device root', now),
                )
            else:
                location_public_id = str(location['public_id'])
                c.execute("UPDATE locations SET status='available',checked_at_us=?,error=NULL WHERE public_id=?", (now, location_public_id))
            c.commit()
        return RegisteredStorage(device_public_id, location_public_id, info.identity, info.label, info.mount_path, info.relative_path)

    def reconcile(self, volumes: dict[str, MountedVolume] | None = None) -> dict[str, str]:
        """Update each known device once and return identity -> status."""
        volumes = mounted_volumes() if volumes is None else volumes
        now = time.time_ns() // 1000
        with self._connect() as c:
            known = list(c.execute("SELECT id,identity,current_mount_path FROM devices"))
            for row in known:
                volume = volumes.get(str(row['identity']))
                if volume is None:
                    c.execute(
                        "UPDATE devices SET status='offline',current_mount_path=NULL,checked_at_us=?,error=NULL WHERE id=?",
                        (now, row['id']),
                    )
                else:
                    c.execute(
                        "UPDATE devices SET label=COALESCE(?,label),status='online',current_mount_path=?,last_mount_path=?,last_seen_at_us=?,checked_at_us=?,error=NULL WHERE id=?",
                        (volume.label, str(volume.mount_path), str(volume.mount_path), now, now, row['id']),
                    )
            # Location reachability is derived from its device unless a later
            # targeted location check records a more specific failure.
            c.execute("UPDATE locations SET status='available',checked_at_us=?,error=NULL WHERE device_id IN (SELECT id FROM devices WHERE status='online')", (now,))
            c.execute("UPDATE locations SET status='unknown',checked_at_us=? WHERE device_id IN (SELECT id FROM devices WHERE status='offline')", (now,))
            c.commit()
            return {str(r['identity']): str(r['status']) for r in c.execute("SELECT identity,status FROM devices")}

    def resolve(self, device_public_id: str | None, relative_path: str | None) -> Path | None:
        if not device_public_id or relative_path is None:
            return None
        with self._connect() as c:
            row = c.execute("SELECT status,current_mount_path FROM devices WHERE public_id=?", (device_public_id,)).fetchone()
        if row is None or row['status'] != 'online' or not row['current_mount_path']:
            return None
        return Path(str(row['current_mount_path'])) / Path(relative_path)

    def device_status(self, device_public_id: str | None) -> str:
        if not device_public_id:
            return 'unknown'
        with self._connect() as c:
            row = c.execute("SELECT status FROM devices WHERE public_id=?", (device_public_id,)).fetchone()
        return str(row['status']) if row else 'unknown'

    def list_devices(self) -> list[sqlite3.Row]:
        with self._connect() as c:
            return list(c.execute("SELECT * FROM devices ORDER BY label,identity"))
