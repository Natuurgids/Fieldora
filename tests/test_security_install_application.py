from __future__ import annotations

import hashlib

import pytest

from natureai_next.application.security_install import require_security_install
from natureai_next.domain.access_control import Identity, IdentityKind, Policy, PolicyEffect, PolicySource
from natureai_next.domain.security_install import SecurityInstallAcceptanceError, canonical_sha256
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository


def _evidence(payload: bytes, *, provider_id: str = "fieldora-bastion") -> dict[str, object]:
    sha256 = hashlib.sha256(payload).hexdigest()
    release_digest = "a" * 64
    compatibility_payload = {
        "release_id": "release-42",
        "component": "fieldora",
        "version": "5.5.0",
    }
    return {
        "protocol_version": 1,
        "release_id": "release-42",
        "package_id": "fieldora-5.5.0.whl",
        "release_digest": release_digest,
        "target": {
            "component": "fieldora",
            "version": "5.5.0",
            "compatible_from": ["5.4.0"],
        },
        "artifact": {
            "package_id": "fieldora-5.5.0.whl",
            "sha256": sha256,
            "size": len(payload),
        },
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
            "package_id": "fieldora-5.5.0.whl",
            "collector_id": "fieldora-device-17",
            "expected_sha256": sha256,
            "observed_sha256": sha256,
            "status": "accepted",
        },
        "independent_verification": {
            "verified": True,
            "package_id": "fieldora-5.5.0.whl",
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


def test_trusted_boundary_uses_real_pbac_and_accepts_alternate_provider(tmp_path) -> None:
    payload = b"trusted release"
    artifact = tmp_path / "fieldora.whl"
    artifact.write_bytes(payload)
    database = tmp_path / "access-control.sqlite3"
    _allow_install(database)

    accepted = require_security_install(
        _evidence(payload, provider_id="alternate-transfer"),
        artifact_path=artifact,
        access_control_database=database,
        subject_id="installer",
        expected_package_id="fieldora-5.5.0.whl",
        expected_target_component="fieldora",
        actual_target_version="5.4.0",
    )

    assert accepted.secure_transfer_provider == "alternate-transfer"
    assert accepted.matched_policy_ids == ("allow-security-install",)


def test_trusted_boundary_fails_closed_without_policy(tmp_path) -> None:
    payload = b"trusted release"
    artifact = tmp_path / "fieldora.whl"
    artifact.write_bytes(payload)
    database = tmp_path / "access-control.sqlite3"
    repository = SqliteAccessControlRepository(database)
    repository.put_identity(
        Identity("installer", IdentityKind.SERVICE, "Security installer", "platform")
    )

    with pytest.raises(SecurityInstallAcceptanceError, match="business authorization denied"):
        require_security_install(
            _evidence(payload),
            artifact_path=artifact,
            access_control_database=database,
            subject_id="installer",
            expected_package_id="fieldora-5.5.0.whl",
            expected_target_component="fieldora",
            actual_target_version="5.4.0",
        )


def test_trusted_boundary_rehashes_artifact_after_tampering(tmp_path) -> None:
    original = b"trusted release"
    artifact = tmp_path / "fieldora.whl"
    artifact.write_bytes(original)
    evidence = _evidence(original)
    database = tmp_path / "access-control.sqlite3"
    _allow_install(database)
    artifact.write_bytes(b"tampered after evidence")

    with pytest.raises(SecurityInstallAcceptanceError, match="artifact"):
        require_security_install(
            evidence,
            artifact_path=artifact,
            access_control_database=database,
            subject_id="installer",
            expected_package_id="fieldora-5.5.0.whl",
            expected_target_component="fieldora",
            actual_target_version="5.4.0",
        )
