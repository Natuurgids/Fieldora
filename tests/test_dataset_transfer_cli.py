from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from natureai_next.bootstrap.dataset_transfer_cli import (
    DatasetTransferError,
    install_dataset_transfer,
    main,
    verify_dataset_transfer,
)
from natureai_next.domain.access_control import Identity, IdentityKind, Policy, PolicyEffect, PolicySource
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository
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



def _allow_install(database: Path, subject: str = "installer") -> None:
    repository = SqliteAccessControlRepository(database)
    repository.put_identity(Identity(subject, IdentityKind.SERVICE, "Dataset installer", "platform"))
    repository.put_policy(Policy(
        policy_id="allow-dataset-install", name="Allow dataset install",
        effect=PolicyEffect.ALLOW, source=PolicySource.DIRECT, source_id="",
        subject_id=subject, role_id="", actions=("install",),
        resource_types=("security_install_release",), purposes=("security_install",),
    ))


def test_dataset_install_is_pbac_gated_and_atomic(tmp_path: Path) -> None:
    artifact, evidence, signature, public = _transfer(tmp_path)
    database = tmp_path / "access.sqlite3"
    _allow_install(database)
    verified, destination = install_dataset_transfer(
        artifact, evidence, signature, public, tmp_path / "store",
        security_install_subject="installer", access_control_database=database,
    )
    assert destination == tmp_path / "store" / "map_dataset" / "base" / "1"
    assert (destination / artifact.name).read_bytes() == artifact.read_bytes()
    receipt = json.loads((destination / "FIELDORA-INSTALL.json").read_text())
    assert receipt["release_id"] == verified.release.release_id
    assert receipt["network"] == "offline"


def test_dataset_install_denied_by_pbac_does_not_activate(tmp_path: Path) -> None:
    artifact, evidence, signature, public = _transfer(tmp_path)
    database = tmp_path / "access.sqlite3"
    repository = SqliteAccessControlRepository(database)
    repository.put_identity(Identity("installer", IdentityKind.SERVICE, "Dataset installer", "platform"))
    store = tmp_path / "store"
    with pytest.raises(DatasetTransferError, match="business authorization denied"):
        install_dataset_transfer(
            artifact, evidence, signature, public, store,
            security_install_subject="installer", access_control_database=database,
        )
    assert not (store / "map_dataset" / "base" / "1").exists()



def test_dataset_receiver_cli_verify(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    artifact, evidence, signature, public = _transfer(tmp_path)
    result = main([
        "verify", str(artifact), "--evidence", str(evidence), "--signature", str(signature),
        "--trusted-signing-key", str(public),
    ])
    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["artifact_type"] == "map_dataset"


def test_dataset_receiver_cli_install_with_sqlite_pbac(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifact, evidence, signature, public = _transfer(tmp_path)
    database = tmp_path / "access.sqlite3"
    _allow_install(database)
    result = main([
        "install", str(artifact), "--evidence", str(evidence), "--signature", str(signature),
        "--trusted-signing-key", str(public), "--store", str(tmp_path / "store"),
        "--security-install-subject", "installer", "--access-control-database", str(database),
    ])
    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert Path(output["destination"]).is_dir()
