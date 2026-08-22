from pathlib import Path

from natureai_next.application.health import LibraryHealthService
from natureai_next.infrastructure.subsystems.registry import (
    SubsystemDatabaseDescriptor, SubsystemDatabaseRegistry,
)


def test_health_service_uses_registry_keys_contract(tmp_path: Path):
    registry = SubsystemDatabaseRegistry(
        (SubsystemDatabaseDescriptor("optional.test", tmp_path / "optional.sqlite3", ()),),
        "4.0.0.dev1+build34",
    )
    service = object.__new__(LibraryHealthService)
    service._subsystems = registry
    checks = service._subsystem_checks()
    assert len(checks) == 1
    assert checks[0].key == "subsystem:optional.test"
