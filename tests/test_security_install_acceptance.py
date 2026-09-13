from __future__ import annotations

import copy
import hashlib

import pytest

from natureai_next.domain.access_control import AccessDecision
from natureai_next.domain.security_install import (
    SecurityInstallAcceptanceError,
    accept_security_install_release,
    canonical_sha256,
)


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


def _accept(tmp_path, evidence, payload: bytes = b"trusted release"):
    artifact = tmp_path / "fieldora.whl"
    artifact.write_bytes(payload)
    return accept_security_install_release(
        evidence,
        artifact_path=artifact,
        expected_package_id="fieldora-5.5.0.whl",
        expected_target_component="fieldora",
        actual_target_version="5.4.0",
        business_authorization=AccessDecision(
            allowed=True,
            reason="policy allowed",
            matched_policy_ids=("install-fieldora",),
        ),
    )


def test_accepts_bastion_shaped_secure_transfer_receipt(tmp_path) -> None:
    payload = b"trusted release"
    accepted = _accept(tmp_path, _evidence(payload), payload)
    assert accepted.secure_transfer_provider == "fieldora-bastion"
    assert accepted.collector_id == "fieldora-device-17"
    assert accepted.matched_policy_ids == ("install-fieldora",)


def test_provider_is_replaceable_when_semantics_are_equivalent(tmp_path) -> None:
    payload = b"trusted release"
    accepted = _accept(tmp_path, _evidence(payload, provider_id="alternate-transfer"), payload)
    assert accepted.secure_transfer_provider == "alternate-transfer"


def test_fieldora_pbac_is_required_independently(tmp_path) -> None:
    payload = b"trusted release"
    artifact = tmp_path / "fieldora.whl"
    artifact.write_bytes(payload)
    with pytest.raises(SecurityInstallAcceptanceError, match="business authorization denied"):
        accept_security_install_release(
            _evidence(payload),
            artifact_path=artifact,
            expected_package_id="fieldora-5.5.0.whl",
            expected_target_component="fieldora",
            actual_target_version="5.4.0",
            business_authorization=AccessDecision(False, "denied"),
        )


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("protocol_version",), 2, "protocol version"),
        (("package_id",), "other.whl", "package identity mismatch"),
        (("target", "component"), "other", "target component mismatch"),
        (("target", "compatible_from"), ["5.3.0"], "not approved"),
        (("artifact", "size"), 1, "artifact size mismatch"),
        (("artifact", "sha256"), "b" * 64, "artifact digest mismatch"),
        (("compatibility_approval", "approval_digest"), "b" * 64, "approval digest mismatch"),
        (("commercial_private_supply_chain", "approved"), False, "supply-chain"),
        (("provenance", "signature_verified"), False, "signature/provenance"),
        (("secure_transfer", "capability"), "something-else", "capability mismatch"),
        (("secure_transfer", "approved"), False, "not approved"),
        (("transfer_receipt", "status"), "rejected", "not accepted"),
        (("transfer_receipt", "observed_sha256"), "b" * 64, "artifact digest mismatch"),
        (("independent_verification", "verified"), False, "not verified"),
        (("independent_verification", "release_digest"), "b" * 64, "release digest mismatch"),
    ],
)
def test_acceptance_fails_closed_on_tampering(tmp_path, path, value, message) -> None:
    payload = b"trusted release"
    evidence = copy.deepcopy(_evidence(payload))
    target = evidence
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(SecurityInstallAcceptanceError, match=message):
        _accept(tmp_path, evidence, payload)


@pytest.mark.parametrize(
    "field",
    [
        "compatibility_approval",
        "commercial_private_supply_chain",
        "provenance",
        "secure_transfer",
        "transfer_receipt",
        "independent_verification",
    ],
)
def test_required_evidence_cannot_be_omitted(tmp_path, field) -> None:
    payload = b"trusted release"
    evidence = _evidence(payload)
    evidence.pop(field)
    with pytest.raises(SecurityInstallAcceptanceError):
        _accept(tmp_path, evidence, payload)
