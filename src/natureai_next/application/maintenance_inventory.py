"""Maintenance inventory models and read contract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StorageEntry:
    key: str
    title: str
    path: Path
    size_bytes: int
    file_count: int
    authoritative: bool


@dataclass(frozen=True, slots=True)
class PackageEntry:
    subsystem: str
    public_id: str
    name: str
    version: str
    enabled: bool
    status: str
    size_bytes: int
    license_name: str = ""
    attribution: str = ""
    path: Path | None = None


@dataclass(frozen=True, slots=True)
class MaintenanceInventory:
    storage: tuple[StorageEntry, ...]
    packages: tuple[PackageEntry, ...]

    @property
    def total_bytes(self) -> int:
        return sum(item.size_bytes for item in self.storage)


class MaintenanceInventoryReader(Protocol):
    """Read Aperture-owned storage and package projections without mutation."""

    def inspect(self) -> MaintenanceInventory: ...
