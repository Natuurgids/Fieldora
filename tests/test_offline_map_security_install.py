from __future__ import annotations

import hashlib

import pytest

from natureai_next import __version__
from natureai_next.domain.access_control import Identity, IdentityKind, Policy, PolicyEffect, PolicySource
from natureai_next.domain.maps import OfflineMapPackage
from natureai_next.domain.security_install import SecurityInstallAcceptanceError, canonical_sha256
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository
from natureai_next.infrastructure.subsystems.maps import OfflineMapCatalog


class _RecordingConnection:
    def __init__(self) -> None:
        self.executed = False

    def execute(self, *_args, **_kwargs):
        self.executed = True
        return None

    def close(self) -> None:
        pass


class _RecordingFactory:
    def __init__(self) -> None:
        self.connections = 0
        self.connection = _RecordingConnection()

    def connect(self, *_args, **_kwargs):
        self.connections += 1
        return self.connection


def _package(path) -> OfflineMapPackage:
    payload = path.read_bytes()
    return OfflineMapPackage(
        public_id="map-1",
        provider_key="offline",
        package_name="Test map",
        package_version="2026.09",
        format="pmtiles",
        package_path=str(path),
        installed_at_us=1,
        checksum_sha256=hashlib.sha256(payload).hexdigest(),
    )


def _evidence(path, *, provider_id: str = "fieldora-bastion") -> dict[str, object]:
    payload = path.read_bytes()
    sha256 = hashlib.sha256(payload).hexdigest()
    release_digest = "b" * 64
    compatibility_payload = {
        "release_id": "maps-release-1",
        "component": "offline-maps",
        "version": "2026.09",
    }
    return {
        "protocol_version": 1,
        "release_id": "maps-release-1",
        "package_id": path.name,
        "release_digest": release_digest,
        "target": {
            "component": "offline-maps",
            "version": "2026.09",
            "compatible_from": [__version__],
        },
        "artifact": {"package_id": path.name, "sha256": sha256, "size": len(payload)},
        "compatibility_approval": {
            "approved": True,
            "payload": compatibility_payload,
            "approval_digest": canonical_sha256(compatibility_payload),
        },
        "commercial_private_supply_chain": {
            "approved": True,
            "private_distribution": True,
        },
        "provenance": {
            "signature_verified": True,
            "provenance_verified": True,
            "release_digest": release_digest,
        },
        "secure_transfer": {
            "provider_id": provider_id,
            "capability": "secure-transfer",
            "protocol_version": 1,
            "approved": True,
            "release_digest": release_digest,
        },
        "transfer_receipt": {
            "package_id": path.name,
            "collector_id": "fieldora-device-17",
            "expected_sha256": sha256,
            "observed_sha256": sha256,
            "status": "accepted",
        },
        "independent_verification": {
            "verified": True,
            "package_id": path.name,
            "release_digest": release_digest,
            "sha256": sha256,
        },
    }


def _allow_install(database, subject: str = "installer") -> None:
    repository = SqliteAccessControlRepository(database)
    repository.put_identity(
        Identity(subject, IdentityKind.SERVICE, "Security installer", "platform")
    )
    repository.put_policy(
        Policy(
            policy_id="allow-security-install",
            name="Allow governed release install",
            effect=PolicyEffect.ALLOW,
            source=PolicySource.DIRECT,
            source_id="",
            subject_id=subject,
            role_id="",
            actions=("install",),
            resource_types=("security_install_release",),
            purposes=("security_install",),
        )
    )


def test_map_registration_requires_security_install_before_catalog_mutation(tmp_path) -> None:
    artifact = tmp_path / "map.pmtiles"
    artifact.write_bytes(b"map-bytes")
    factory = _RecordingFactory()
    catalog = OfflineMapCatalog(factory)

    with pytest.raises(SecurityInstallAcceptanceError, match="evidence is required"):
        catalog.register(_package(artifact))

    assert factory.connections == 0


def test_map_registration_rehashes_tampered_artifact_before_catalog_mutation(tmp_path) -> None:
    artifact = tmp_path / "map.pmtiles"
    artifact.write_bytes(b"map-bytes")
    evidence = _evidence(artifact)
    artifact.write_bytes(b"tampered-map")
    database = tmp_path / "access-control.sqlite3"
    _allow_install(database)
    factory = _RecordingFactory()
    catalog = OfflineMapCatalog(factory)

    with pytest.raises(SecurityInstallAcceptanceError, match="artifact"):
        catalog.register(
            _package(artifact),
            security_install_evidence=evidence,
            access_control_database=database,
            subject_id="installer",
        )

    assert factory.connections == 0


def test_map_registration_uses_real_pbac_and_accepts_alternate_provider(tmp_path) -> None:
    artifact = tmp_path / "map.pmtiles"
    artifact.write_bytes(b"map-bytes")
    database = tmp_path / "access-control.sqlite3"
    _allow_install(database)
    factory = _RecordingFactory()
    catalog = OfflineMapCatalog(factory)

    catalog.register(
        _package(artifact),
        security_install_evidence=_evidence(artifact, provider_id="alternate-transfer"),
        access_control_database=database,
        subject_id="installer",
    )

    assert factory.connections == 1
    assert factory.connection.executed


def test_map_registration_denied_by_pbac_never_opens_catalog(tmp_path) -> None:
    artifact = tmp_path / "map.pmtiles"
    artifact.write_bytes(b"map-bytes")
    database = tmp_path / "access-control.sqlite3"
    repository = SqliteAccessControlRepository(database)
    repository.put_identity(
        Identity("installer", IdentityKind.SERVICE, "Security installer", "platform")
    )
    factory = _RecordingFactory()
    catalog = OfflineMapCatalog(factory)

    with pytest.raises(SecurityInstallAcceptanceError, match="business authorization denied"):
        catalog.register(
            _package(artifact),
            security_install_evidence=_evidence(artifact),
            access_control_database=database,
            subject_id="installer",
        )

    assert factory.connections == 0
