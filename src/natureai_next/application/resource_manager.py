"""Shared resource acquisition planning for offline-first data packages."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class AcquisitionKind(str, Enum):
    CURRENT = "current"
    DELTA = "delta"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class ResourceState:
    resource_id: str
    version: str | None
    checksum: str | None = None
    installed_parts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResourceManifest:
    resource_id: str
    version: str
    checksum: str
    parts: tuple[str, ...] = ()
    delta_from: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AcquisitionPlan:
    kind: AcquisitionKind
    missing_parts: tuple[str, ...]
    reason: str
    inspected_local: bool = True


class ResourceManager:
    """Select the smallest safe acquisition before any large transfer begins."""

    def plan(self, local: ResourceState | None, remote: ResourceManifest) -> AcquisitionPlan:
        if local is None or local.version is None:
            return AcquisitionPlan(
                AcquisitionKind.FULL, remote.parts, "No local resource is installed."
            )
        missing = tuple(part for part in remote.parts if part not in set(local.installed_parts))
        if local.version == remote.version and local.checksum == remote.checksum and not missing:
            return AcquisitionPlan(
                AcquisitionKind.CURRENT, (), "The installed resource is current."
            )
        if local.version in remote.delta_from:
            parts = missing or remote.parts
            return AcquisitionPlan(
                AcquisitionKind.DELTA, parts, "A compatible incremental update is available."
            )
        return AcquisitionPlan(
            AcquisitionKind.FULL, remote.parts, "No compatible incremental update is available."
        )

    @staticmethod
    def unique_missing(requested: Iterable[str], installed: Iterable[str]) -> tuple[str, ...]:
        have = set(installed)
        return tuple(dict.fromkeys(item for item in requested if item not in have))
