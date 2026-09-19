from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from natureai_next.bootstrap.dataset_transfer_cli import DatasetTransferError, verify_dataset_transfer
from natureai_next.domain.security_install import canonical_sha256


def _transfer(tmp_path: Path):
    key = Ed25519PrivateKey.generate()
    private_der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    key_id = hashlib.sha256(private_der).hexdigest()[:32]
    public = tmp_path / "trusted.pem"
    public.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ))
    artifact = tmp_path / "map_dataset-base-1.zip"
    artifact.write_bytes(b"PK-test-dataset")
    artifact_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    release = {
        "artifact_type": "map_dataset", "artifact_id": "base", "version": "1",
        "package_sha256": artifact_sha, "signer_key_id": key_id,
    }
    evidence = {
        "protocol_version": 2,
        "release_id": "fieldora-artifact:map_dataset:base:1",
        "artifact_type": "map_dataset", "artifact_id": "base", "version": "1",
        "payload_sha256": "a" * 64, "file_count": 1,
        "artifact": {"package_id": artifact.name, "sha256": artifact_sha, "size": artifact.stat().st_size},
        "release_digest": canonical_sha256(release), "signer_key_id": key_id,
        "source_provenance": {"source_id": "maps"},
        "type_validation": {"approved": True, "validator": "map"},
        "secure_transfer": {"provider_id": "fieldora-bastion", "capability": "certified-artifact-transfer", "protocol_version": 2},
    }
    evidence_path = tmp_path / "evidence.json"
    evidence_bytes = (json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n").encode()
    evidence_path.write_bytes(evidence_bytes)
    signature = tmp_path / "evidence.sig"
    signature.write_text(json.dumps({
        "algorithm": "ed25519", "key_id": key_id,
        "signature": base64.b64encode(key.sign(evidence_bytes)).decode(),
    }, sort_keys=True, separators=(",", ":")) + "\n")
    return artifact, evidence_path, signature, public


def test_verifies_signed_dataset_transfer(tmp_path: Path) -> None:
    artifact, evidence, signature, public = _transfer(tmp_path)
    verified = verify_dataset_transfer(artifact, evidence, signature, public)
    assert verified.artifact_type == "map_dataset"
    assert verified.release.release_id == "fieldora-artifact:map_dataset:base:1"
    assert verified.release.signer_key_id


def test_rejects_tampered_signed_evidence(tmp_path: Path) -> None:
    artifact, evidence, signature, public = _transfer(tmp_path)
    data = json.loads(evidence.read_text())
    data["version"] = "2"
    evidence.write_text(json.dumps(data))
    with pytest.raises(DatasetTransferError, match="signature verification failed"):
        verify_dataset_transfer(artifact, evidence, signature, public)


def test_rejects_tampered_artifact(tmp_path: Path) -> None:
    artifact, evidence, signature, public = _transfer(tmp_path)
    artifact.write_bytes(b"changed")
    with pytest.raises(DatasetTransferError, match="size mismatch|digest mismatch"):
        verify_dataset_transfer(artifact, evidence, signature, public)
