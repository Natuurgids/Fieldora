from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_COMPOSE = ROOT / "deployment" / "storage-node" / "compose.yaml"
SAME_HOST_COMPOSE = ROOT / "deployment" / "storage-node" / "compose.same-host.yaml"
README = ROOT / "deployment" / "storage-node" / "README.md"


def test_linked_storage_archive_mount_is_read_only_and_hardened() -> None:
    text = BASE_COMPOSE.read_text(encoding="utf-8")

    assert "${FIELDORA_STORAGE_ROOT:?Set FIELDORA_STORAGE_ROOT to the organisation archive path}:/mnt/fieldora-storage:ro" in text
    assert "${FIELDORA_STORAGE_TRUST_DIR:?Set FIELDORA_STORAGE_TRUST_DIR to the enrolled service trust directory}:/run/fieldora-trust:ro" in text
    assert "    read_only: true" in text
    assert "      - no-new-privileges:true" in text
    assert "    cap_drop:\n      - ALL" in text


def test_same_host_profile_uses_only_private_fieldora_network() -> None:
    text = SAME_HOST_COMPOSE.read_text(encoding="utf-8")

    assert "      - fieldora-platform" in text
    assert "    external: true" in text
    assert "    name: ${FIELDORA_PLATFORM_NETWORK:-fieldora_fieldora-network}" in text
    assert "https://fieldora-server:8765" in text
    assert "WAN route, Bastion, or cloud service" in text


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
