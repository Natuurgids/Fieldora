from pathlib import Path

from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS
from natureai_next.infrastructure.storage_devices import DeviceRegistry, MountedVolume


def test_build28_3_adds_registry_references():
    migration = next(m for m in CORE_MIGRATIONS if m.number == 29)
    assert "device_public_id" in migration.sql
    assert "location_public_id" in migration.sql


def test_device_reconciliation_updates_one_device_not_item_rows(tmp_path, monkeypatch):
    registry = DeviceRegistry(tmp_path / "storage_devices.db")
    mount = tmp_path / "archive"
    mount.mkdir()

    class Info:
        identity = "volume:archive"
        label = "Archive"
        mount_path = mount
        relative_path = "photos/a.jpg"

    monkeypatch.setattr("natureai_next.infrastructure.storage_devices.identify_path", lambda _path: Info())
    first = registry.register_path(mount / "photos/a.jpg")
    second = registry.register_path(mount / "videos/b.mp4")
    assert first.device_public_id == second.device_public_id
    assert first.location_public_id == second.location_public_id
    assert len(registry.list_devices()) == 1

    registry.reconcile({})
    assert registry.device_status(first.device_public_id) == "offline"
    assert registry.resolve(first.device_public_id, "photos/a.jpg") is None

    registry.reconcile({"volume:archive": MountedVolume("volume:archive", "Archive", Path("H:/"))})
    assert registry.device_status(first.device_public_id) == "online"
    assert registry.resolve(first.device_public_id, "photos/a.jpg") == Path("H:/") / "photos/a.jpg"
