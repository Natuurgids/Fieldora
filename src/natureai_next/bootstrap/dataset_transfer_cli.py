"""Verify standalone Bastion dataset transfers before Fieldora authorization/import."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from natureai_next.domain.security_install import AuthenticatedReleaseContext, canonical_sha256, file_sha256

_ALLOWED_TYPES = {"map_dataset", "biodiversity_dataset"}
_MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
_MAX_SIGNATURE_BYTES = 16 * 1024


class DatasetTransferError(ValueError):
    """Raised when a Bastion dataset transfer cannot be independently authenticated."""


@dataclass(frozen=True, slots=True)
class VerifiedDatasetTransfer:
    artifact_type: str
    artifact_id: str
    version: str
    package_id: str
    payload_sha256: str
    file_count: int
    release: AuthenticatedReleaseContext
    evidence: dict[str, object]


def verify_dataset_transfer(
    artifact_path: Path,
    evidence_path: Path,
    signature_path: Path,
    trusted_signing_key: Path,
) -> VerifiedDatasetTransfer:
    for path, label, limit in (
        (evidence_path, "evidence", _MAX_EVIDENCE_BYTES),
        (signature_path, "signature", _MAX_SIGNATURE_BYTES),
        (trusted_signing_key, "trusted signing key", _MAX_SIGNATURE_BYTES),
    ):
        if path.is_symlink() or not path.is_file():
            raise DatasetTransferError(f"{label} must be a regular non-symlink file")
        if path.stat().st_size > limit:
            raise DatasetTransferError(f"{label} exceeds the configured size limit")
    if artifact_path.is_symlink() or not artifact_path.is_file():
        raise DatasetTransferError("artifact must be a regular non-symlink file")

    try:
        evidence_bytes = evidence_path.read_bytes()
        evidence = json.loads(evidence_bytes)
        envelope = json.loads(signature_path.read_text(encoding="utf-8"))
        signature = base64.b64decode(str(envelope.get("signature") or ""), validate=True)
        public_key = serialization.load_pem_public_key(trusted_signing_key.read_bytes())
    except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DatasetTransferError("dataset transfer authentication material is invalid") from exc
    if not isinstance(evidence, dict) or not isinstance(envelope, dict):
        raise DatasetTransferError("dataset transfer evidence and signature must be objects")
    if envelope.get("algorithm") != "ed25519" or not isinstance(public_key, Ed25519PublicKey):
        raise DatasetTransferError("dataset transfer requires an Ed25519 trusted key")
    public_der = public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    key_id = hashlib.sha256(public_der).hexdigest()[:32]
    if str(envelope.get("key_id") or "") != key_id or str(evidence.get("signer_key_id") or "") != key_id:
        raise DatasetTransferError("dataset transfer signer does not match trusted key")
    try:
        public_key.verify(signature, evidence_bytes)
    except InvalidSignature as exc:
        raise DatasetTransferError("dataset transfer evidence signature verification failed") from exc

    artifact_type = str(evidence.get("artifact_type") or "")
    artifact_id = str(evidence.get("artifact_id") or "")
    version = str(evidence.get("version") or "")
    if artifact_type not in _ALLOWED_TYPES or not artifact_id or not version:
        raise DatasetTransferError("dataset transfer identity is invalid")
    artifact = evidence.get("artifact")
    if not isinstance(artifact, dict):
        raise DatasetTransferError("dataset transfer artifact evidence is invalid")
    package_id = str(artifact.get("package_id") or "")
    expected_sha = str(artifact.get("sha256") or "").lower()
    try:
        expected_size = int(artifact.get("size"))
        file_count = int(evidence.get("file_count"))
    except (TypeError, ValueError) as exc:
        raise DatasetTransferError("dataset transfer sizes are invalid") from exc
    if package_id != artifact_path.name or expected_size != artifact_path.stat().st_size:
        raise DatasetTransferError("dataset transfer artifact identity or size mismatch")
    actual_sha = file_sha256(artifact_path)
    if expected_sha != actual_sha:
        raise DatasetTransferError("dataset transfer artifact digest mismatch")
    payload_sha = str(evidence.get("payload_sha256") or "").lower()
    if len(payload_sha) != 64 or any(c not in "0123456789abcdef" for c in payload_sha) or file_count < 1:
        raise DatasetTransferError("dataset transfer payload binding is invalid")
    validation = evidence.get("type_validation")
    if not isinstance(validation, dict) or validation.get("approved") is not True:
        raise DatasetTransferError("dataset transfer type validation is not approved")

    release_payload = {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "version": version,
        "package_sha256": actual_sha,
        "signer_key_id": key_id,
    }
    release_digest = canonical_sha256(release_payload)
    if str(evidence.get("release_digest") or "").lower() != release_digest:
        raise DatasetTransferError("dataset transfer release binding mismatch")
    release_id = f"fieldora-artifact:{artifact_type}:{artifact_id}:{version}"
    if str(evidence.get("release_id") or "") != release_id:
        raise DatasetTransferError("dataset transfer release identity mismatch")

    return VerifiedDatasetTransfer(
        artifact_type, artifact_id, version, package_id, payload_sha, file_count,
        AuthenticatedReleaseContext(release_id, release_digest, key_id), evidence,
    )
