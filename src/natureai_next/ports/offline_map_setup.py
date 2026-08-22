"""Bootstrap-supplied dependencies for the offline-map setup interface."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OfflineMapSetupPlatform:
    """The narrow composition boundary required by offline-map setup."""

    foundation_factory: Callable[[], object]
    map_catalog_factory: Callable[[object], object]
    map_package_service_factory: Callable[[object], object]
    vector_map_converter_factory: Callable[[], object | None]
