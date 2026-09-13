"""Trusted-side acceptance of Security Install release evidence.

The contract is provider-neutral. FieldoraBastion is the default provider for
``secure-transfer``, but provider identity never grants Fieldora business
authorization. A caller must supply a separate Fieldora PBAC decision.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from natureai_next.domain.access_control import AccessDecision

SUPPORTED_SECURITY_INSTALL_PROTOCOL = 1
SECURE_TRANSFER_CAPABILITY = "secure-transfer"


class SecurityInstallAcceptanceError(ValueError):
    """Raised when trusted-side release acceptance must fail closed."""


@dataclass(frozen=True, slots=True)
class TrustedInstallAcceptance:
    """Fieldora-owned acceptance bound to one artifact and PBAC decision."""

    release_id: str
    package_id: str
    release_digest: str
    target_component: str
    target_version: str
    artifact_sha256: str
    artifact_size: int
    secure_transfer_provider: str
    matched_policy_ids: tuple[str, ...]


def canonical_sha256(value: object) -> str:
    """Return the deterministic SHA-256 used for approval payload binding."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _object(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SecurityInstallAcceptanceError(f"missing or invalid {name} evidence")
    return value


def _token(value: object, name: str) -> str:
    token = str(value or "").strip()
    if not token:
        raise SecurityInstallAcceptanceError(f"missing {name}")
    return token


def _sha256(value: object, name: str) -> str:
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise SecurityInstallAcceptanceError(f"invalid {name}")
    return digest


def _approved(evidence: Mapping[str, object], name: str) -> None:
    if evidence.get("approved") is not True:
        raise SecurityInstallAcceptanceError(f"{name} evidence is not approved")


def accept_security_install_release(
    evidence: Mapping[str, object],
    *,
    artifact_path: Path,
    expected_package_id: str,
    expected_target_component: str,
    actual_target_version: str,
    business_authorization: AccessDecision,
) -> TrustedInstallAcceptance:
    """Independently verify release evidence and Fieldora business authorization.

    The artifact digest and size are calculated from the local file. The
    secure-transfer provider is informational; authorization depends on the
    capability/evidence semantics, not a specific provider id.
    """

    if not business_authorization.allowed:
        raise SecurityInstallAcceptanceError("Fieldora business authorization denied")
    if not artifact_path.is_file() or artifact_path.is_symlink():
        raise SecurityInstallAcceptanceError("artifact must be a regular non-symlink file")

    try:
        protocol_version = int(evidence.get("protocol_version"))
    except (TypeError, ValueError) as exc:
        raise SecurityInstallAcceptanceError("invalid Security Install protocol version") from exc
    if protocol_version != SUPPORTED_SECURITY_INSTALL_PROTOCOL:
        raise SecurityInstallAcceptanceError("unsupported Security Install protocol version")

    release_id = _token(evidence.get("release_id"), "release_id")
    package_id = _token(evidence.get("package_id"), "package_id")
    release_digest = _sha256(evidence.get("release_digest"), "release_digest")
    if package_id != expected_package_id:
        raise SecurityInstallAcceptanceError("package identity mismatch")

    target = _object(evidence.get("target"), "target")
    target_component = _token(target.get("component"), "target component")
    target_version = _token(target.get("version"), "target version")
    compatible_from = target.get("compatible_from")
    if target_component != expected_target_component:
        raise SecurityInstallAcceptanceError("target component mismatch")
    if isinstance(compatible_from, list):
        compatible_versions = {str(item).strip() for item in compatible_from if str(item).strip()}
        if actual_target_version not in compatible_versions:
            raise SecurityInstallAcceptanceError("actual target version is not approved")
    elif _token(compatible_from, "compatible_from") != actual_target_version:
        raise SecurityInstallAcceptanceError("actual target version is not approved")

    artifact = _object(evidence.get("artifact"), "artifact")
    artifact_package_id = _token(artifact.get("package_id"), "artifact package_id")
    artifact_sha256 = _sha256(artifact.get("sha256"), "artifact sha256")
    try:
        artifact_size = int(artifact.get("size"))
    except (TypeError, ValueError) as exc:
        raise SecurityInstallAcceptanceError("invalid artifact size") from exc
    if artifact_package_id != package_id:
        raise SecurityInstallAcceptanceError("artifact package identity mismatch")
    actual_size = artifact_path.stat().st_size
    actual_sha256 = file_sha256(artifact_path)
    if artifact_size != actual_size:
        raise SecurityInstallAcceptanceError("artifact size mismatch")
    if artifact_sha256 != actual_sha256:
        raise SecurityInstallAcceptanceError("artifact digest mismatch")

    compatibility = _object(evidence.get("compatibility_approval"), "compatibility approval")
    _approved(compatibility, "compatibility approval")
    compatibility_payload = _object(compatibility.get("payload"), "compatibility approval payload")
    approval_digest = _sha256(compatibility.get("approval_digest"), "compatibility approval digest")
    if approval_digest != canonical_sha256(compatibility_payload):
        raise SecurityInstallAcceptanceError("compatibility approval digest mismatch")
    if _token(compatibility_payload.get("release_id"), "compatibility release_id") != release_id:
        raise SecurityInstallAcceptanceError("compatibility approval release mismatch")
    if _token(compatibility_payload.get("component"), "compatibility component") != target_component:
        raise SecurityInstallAcceptanceError("compatibility approval component mismatch")
    if _token(compatibility_payload.get("version"), "compatibility version") != target_version:
        raise SecurityInstallAcceptanceError("compatibility approval version mismatch")

    supply_chain = _object(evidence.get("commercial_private_supply_chain"), "supply-chain")
    _approved(supply_chain, "commercial-private supply-chain")
    if supply_chain.get("private_distribution") is not True:
        raise SecurityInstallAcceptanceError("commercial-private supply-chain evidence is incomplete")

    provenance = _object(evidence.get("provenance"), "signature/provenance")
    if provenance.get("signature_verified") is not True or provenance.get("provenance_verified") is not True:
        raise SecurityInstallAcceptanceError("signature/provenance evidence is not verified")
    if _sha256(provenance.get("release_digest"), "provenance release_digest") != release_digest:
        raise SecurityInstallAcceptanceError("provenance release digest mismatch")

    transfer = _object(evidence.get("secure_transfer"), "secure-transfer")
    if _token(transfer.get("capability"), "secure-transfer capability") != SECURE_TRANSFER_CAPABILITY:
        raise SecurityInstallAcceptanceError("secure-transfer capability mismatch")
    _approved(transfer, "secure-transfer")
    provider_id = _token(transfer.get("provider_id"), "secure-transfer provider_id")
    try:
        transfer_protocol = int(transfer.get("protocol_version"))
    except (TypeError, ValueError) as exc:
        raise SecurityInstallAcceptanceError("invalid secure-transfer protocol version") from exc
    if transfer_protocol != protocol_version:
        raise SecurityInstallAcceptanceError("secure-transfer protocol version mismatch")
    if _sha256(transfer.get("release_digest"), "secure-transfer release_digest") != release_digest:
        raise SecurityInstallAcceptanceError("secure-transfer release digest mismatch")

    receipt = _object(evidence.get("transfer_receipt"), "transfer receipt")
    if str(receipt.get("status") or "").strip().lower() != "accepted":
        raise SecurityInstallAcceptanceError("transfer receipt is not accepted")
    if receipt.get("independently_verified") is not True:
        raise SecurityInstallAcceptanceError("transfer receipt lacks independent verification")
    if _token(receipt.get("package_id"), "receipt package_id") != package_id:
        raise SecurityInstallAcceptanceError("transfer receipt package identity mismatch")
    if _sha256(receipt.get("release_digest"), "receipt release_digest") != release_digest:
        raise SecurityInstallAcceptanceError("transfer receipt release digest mismatch")
    expected_sha256 = _sha256(receipt.get("expected_sha256"), "receipt expected_sha256")
    observed_sha256 = _sha256(receipt.get("observed_sha256"), "receipt observed_sha256")
    if expected_sha256 != observed_sha256 or observed_sha256 != actual_sha256:
        raise SecurityInstallAcceptanceError("transfer receipt artifact digest mismatch")
    try:
        observed_size = int(receipt.get("observed_size"))
    except (TypeError, ValueError) as exc:
        raise SecurityInstallAcceptanceError("invalid transfer receipt size") from exc
    if observed_size != actual_size:
        raise SecurityInstallAcceptanceError("transfer receipt artifact size mismatch")

    return TrustedInstallAcceptance(
        release_id=release_id,
        package_id=package_id,
        release_digest=release_digest,
        target_component=target_component,
        target_version=target_version,
        artifact_sha256=actual_sha256,
        artifact_size=actual_size,
        secure_transfer_provider=provider_id,
        matched_policy_ids=business_authorization.matched_policy_ids,
    )
