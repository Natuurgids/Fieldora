"""Platform operations injected into the Maintenance Center UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MaintenancePlatform:
    foundation_factory: Callable[[], object]
    map_catalog_factory: Callable[[object], object]
    map_package_service_factory: Callable[[object], object]
    vector_map_converter_factory: Callable[[], object | None]
    integrity_checker: Callable[[object, bool], object]
    validate_database: Callable[[Path], None]
    replace_database: Callable[..., None]
    read_lock_owner: Callable[[Path], object | None]
    process_is_alive: Callable[[int], bool]
