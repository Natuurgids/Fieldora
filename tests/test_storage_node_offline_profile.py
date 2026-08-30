from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BASE_COMPOSE = ROOT / "deployment" / "storage-node" / "compose.yaml"
SAME_HOST_COMPOSE = ROOT / "deployment" / "storage-node" / "compose.same-host.yaml"
README = ROOT / "deployment" / "storage-node" / "README.md"


def test_linked_storage_archive_mount_is_read_only_and_hardened() -> None:
    compose = yaml.safe_load(BASE_COMPOSE.read_text(encoding="utf-8"))
    service = compose["services"]["storage-service"]

    assert any(
        str(volume).startswith("${FIELDORA_STORAGE_ROOT:")
        and str(volume).endswith(":/mnt/fieldora-storage:ro")
        for volume in service["volumes"]
    )
    assert service["read_only"] is True
    assert "no-new-privileges:true" in service["security_opt"]
    assert service["cap_drop"] == ["ALL"]
    assert any(
        str(volume).startswith("${FIELDORA_STORAGE_TRUST_DIR:")
        and str(volume).endswith(":/run/fieldora-trust:ro")
        for volume in service["volumes"]
    )


def test_same_host_profile_uses_only_private_fieldora_network() -> None:
    compose = yaml.safe_load(SAME_HOST_COMPOSE.read_text(encoding="utf-8"))
    service = compose["services"]["storage-service"]
    network = compose["networks"]["fieldora-platform"]

    assert service["networks"] == ["fieldora-platform"]
    assert network["external"] is True
    assert network["name"] == "${FIELDORA_PLATFORM_NETWORK:-fieldora_fieldora-network}"


def test_offline_storage_documentation_keeps_bastion_and_cloud_optional() -> None:
    text = README.read_text(encoding="utf-8")

    assert "do not require\nFieldoraBastion, a public cloud, or an Internet connection" in text
    assert "Direct attached storage on the Fieldora host" in text
    assert "LAN/NAS/network storage" in text
    assert "Bastion is optional" in text
    assert "Cloud is optional" in text
    assert "https://fieldora-server:8765" in text
    assert "SMB/NFS usernames, passwords, access keys" in text
    assert "read-only" in text
