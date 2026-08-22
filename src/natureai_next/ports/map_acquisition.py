"""Application-facing offline-map acquisition contracts."""

from __future__ import annotations

from typing import Protocol

from natureai_next.domain.maps import OfflineMapPackage


class MapPackageVerificationView(Protocol):
    valid: bool
    message: str


class OfflineMapCatalogPort(Protocol):
    def get(self, public_id: str) -> OfflineMapPackage: ...
    def register(self, package: OfflineMapPackage) -> None: ...
    def remove(self, public_id: str) -> None: ...


class OfflineMapPackagePort(Protocol):
    def verify(self, public_id: str) -> MapPackageVerificationView: ...
    def enable(self, public_id: str) -> None: ...
    def disable(self, public_id: str) -> None: ...
