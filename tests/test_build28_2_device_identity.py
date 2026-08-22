from pathlib import Path

from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS
from natureai_next.infrastructure.storage_devices import DevicePath


def test_build28_2_registers_device_identity_migration():
    migration = next(item for item in CORE_MIGRATIONS if item.number == 28)
    assert "device_identity" in migration.sql
    assert "relative_path" in migration.sql


def test_device_path_resolves_against_new_mount():
    location = DevicePath("volume:test", "Archive", Path("D:/"), "Photos/bird.jpg")
    assert location.resolve(Path("F:/")) == Path("F:/") / "Photos/bird.jpg"
