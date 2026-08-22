"""Asset-centric storage policy and health value objects for Build 28."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class AssetStoragePolicy(StrEnum):
    MANAGED = "managed"
    REFERENCED = "referenced"
    HYBRID = "hybrid"


class StorageProviderKind(StrEnum):
    APERTURE_LIBRARY = "aperture_library"
    LOCAL_FILESYSTEM = "local_filesystem"
    REMOVABLE_VOLUME = "removable_volume"
    NETWORK_SHARE = "network_share"
    CLOUD_SYNC = "cloud_sync"
    CAMERA_DEVICE = "camera_device"
    UNKNOWN = "unknown"


class StorageLocationRole(StrEnum):
    SOURCE = "source"
    APERTURE_MASTER = "aperture_master"


class StorageHealth(StrEnum):
    AVAILABLE = "available"
    OFFLINE = "offline"
    MISSING = "missing"
    CHANGED = "changed"
    CORRUPT = "corrupt"
    PERMISSION_DENIED = "permission_denied"
    CLOUD_PLACEHOLDER = "cloud_placeholder"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class StorageLocation:
    id: int
    asset_id: int
    provider_id: int
    role: StorageLocationRole
    path: Path
    file_size: int | None
    sha256: str | None
    health: StorageHealth
    is_primary: bool
    last_verified_at_us: int | None


@dataclass(frozen=True, slots=True)
class AssetStorageSummary:
    asset_id: int
    asset_public_id: str
    policy: AssetStoragePolicy
    source: StorageLocation | None
    aperture_master: StorageLocation | None

    @property
    def available_location(self) -> StorageLocation | None:
        for location in (self.aperture_master, self.source):
            if location is not None and location.health is StorageHealth.AVAILABLE:
                return location
        return self.aperture_master or self.source
