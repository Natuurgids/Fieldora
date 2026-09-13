from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

import natureai_next.bootstrap.model_bundle_cli as model_bundle_cli
from natureai_next.bootstrap.model_bundle_cli import (
    ModelBundleError,
    install_model_bundle,
    verify_model_bundle,
)
from natureai_next.domain.access_control import (
    Identity,
    IdentityKind,
    Policy,
    PolicyEffect,
    PolicySource,
)
from natureai_next.domain.security_install import canonical_sha256
from natureai_next.infrastructure.database.access_control import SqliteAccessControlRepository


def _write_bundle(
    root: Path,
    files: dict[str, bytes],
    *,
    model_id: str = "fieldora-test-model",
    version: str = "1.0.0",
) -> Path:
    root.mkdir()
    manifest_files = []
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        manifest_files.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "model_id": model_id,
                "version": version,
                "source": "offline-certification",
                "license_id": "test-only",
                "files": manifest_files,
            }
        ),
        encoding="utf-8",
    )
    return root


def _zip_bundle(bundle: Path, archive: Path) -> Path:
    with ZipFile(archive, "w") as output:
        for path in sorted(bundle.rglob("*")):
            if path.is_file() and not path.is_symlink():
                output.write(path, path.relative_to(bundle).as_posix())
    return archive


def _evidence(
    artifact: Path,
    *,
    model_id: str = "fieldora-test-model",
    version: str = "1.0.0",
    provider_id: str = "fieldora-bastion",
) -> dict[str, object]:
    payload = artifact.read_bytes()
    sha256 = hashlib.sha256(payload).hexdigest()
    release_digest = "a" * 64
    component = f"fieldora-model:{model_id}"
    compatibility_payload = {
        "release_id": "model-release-42",
        "component": component,
        "version": version,
    }
    return {
        "protocol_version": 1,
        "release_id": "model-release-42",
        "package_id": artifact.name,
        "release_digest": release_digest,
        "target": {
            "component": component,
            "version": version,
            "compatible_from": ["not-installed"],
        },
        "artifact": {
            "package_id": artifact.name,
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
            "package_id": artifact.name,
            "collector_id": "fieldora-device-17",
            "expected_sha256": sha256,
            "observed_sha256": sha256,
            "status": "accepted",
        },
        "independent_verification": {
            "verified": True,
            "package_id": artifact.name,
            "release_digest": release_digest,
            "sha256": sha256,
        },
    }


def _allow_install(database: Path, subject: str = "installer") -> None:
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


def _install_kwargs(tmp_path: Path, bundle: Path, *, provider_id: str = "fieldora-bastion"):
    artifact = _zip_bundle(bundle, tmp_path / "model-bundle.zip")
    database = tmp_path / "access-control.sqlite3"
    _allow_install(database)
    return artifact, database, {
        "security_install_artifact": artifact,
        "security_install_evidence": _evidence(artifact, provider_id=provider_id),
        "access_control_database": database,
        "security_install_subject": "installer",
        "actual_target_version": "not-installed",
    }


def test_verifies_safe_model_bundle_with_per_file_hashes(tmp_path: Path) -> None:
    bundle = _write_bundle(
        tmp_path / "bundle",
        {
            "model/model.safetensors": b"safe-model-bytes",
            "model/config.json": b'{"architecture":"test"}',
            "model/tokenizer.json": b'{"version":1}',
        },
    )

    verified = verify_model_bundle(bundle)

    assert verified.model_id == "fieldora-test-model"
    assert verified.version == "1.0.0"
    assert verified.registry_id == "fieldora-test-model@1.0.0"
    assert verified.total_bytes == sum(int(item["size_bytes"]) for item in verified.files)
    assert {item["path"] for item in verified.files} == {
        "model/model.safetensors",
        "model/config.json",
        "model/tokenizer.json",
    }


def test_rejects_hash_mismatch(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "bundle", {"model/model.onnx": b"expected"})
    (bundle / "model/model.onnx").write_bytes(b"tampered")

    with pytest.raises(ModelBundleError, match="size mismatch|SHA-256 mismatch"):
        verify_model_bundle(bundle)


def test_rejects_pickle_and_executable_artifacts(tmp_path: Path) -> None:
    for filename in ("model.pkl", "weights.pt", "loader.py", "setup.sh"):
        bundle = _write_bundle(tmp_path / filename.replace(".", "-"), {filename: b"unsafe"})
        with pytest.raises(ModelBundleError, match="unsupported or executable"):
            verify_model_bundle(bundle)


def test_rejects_manifest_path_traversal(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (tmp_path / "escape.gguf").write_bytes(b"escape")
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "model_id": "model",
                "version": "1",
                "files": [
                    {
                        "path": "../escape.gguf",
                        "sha256": hashlib.sha256(b"escape").hexdigest(),
                        "size_bytes": 6,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ModelBundleError, match="unsafe bundle path"):
        verify_model_bundle(bundle)


def test_rejects_symlinked_artifact(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    target = tmp_path / "actual.gguf"
    target.write_bytes(b"model")
    link = bundle / "model.gguf"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable on this test platform")
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "model_id": "model",
                "version": "1",
                "files": [
                    {
                        "path": "model.gguf",
                        "sha256": hashlib.sha256(b"model").hexdigest(),
                        "size_bytes": 5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ModelBundleError, match="regular non-symlink"):
        verify_model_bundle(bundle)


def test_enforces_total_bundle_limit(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "bundle", {"model.gguf": b"0123456789"})

    with pytest.raises(ModelBundleError, match="maximum total size"):
        verify_model_bundle(bundle, max_total_bytes=9)


def test_install_fails_closed_without_security_install_context(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "bundle", {"model/model.onnx": b"model"})
    store = tmp_path / "store"

    with pytest.raises(TypeError):
        install_model_bundle(bundle, store)

    assert not store.exists()


def test_install_is_gated_atomic_and_accepts_alternate_transfer_provider(tmp_path: Path) -> None:
    bundle = _write_bundle(
        tmp_path / "bundle",
        {"model/model.safetensors": b"model", "model/config.json": b"{}"},
    )
    store = tmp_path / "store"
    _artifact, _database, kwargs = _install_kwargs(
        tmp_path, bundle, provider_id="alternate-transfer"
    )

    verified, destination = install_model_bundle(bundle, store, **kwargs)

    assert destination == store / "fieldora-test-model" / "1.0.0"
    assert (destination / "model/model.safetensors").read_bytes() == b"model"
    receipt = json.loads((destination / "FIELDORA-INSTALL.json").read_text(encoding="utf-8"))
    assert receipt["id"] == "fieldora-test-model@1.0.0"
    assert receipt["model_id"] == verified.model_id
    assert receipt["project_id"] == "platform"
    assert receipt["provider_id"] == "fieldora-offline"
    assert receipt["network"] == "offline"
    assert receipt["verification"] == "sha256-per-file"
    assert receipt["artifact_total_bytes"] == verified.total_bytes
    assert receipt["artifact_storage_id"] == "model:fieldora-test-model:1.0.0"
    assert "artifact_store_path" not in receipt
    assert str(store) not in json.dumps(receipt)

    with pytest.raises(ModelBundleError, match="already installed"):
        install_model_bundle(bundle, store, **kwargs)


def test_install_denied_by_real_pbac_does_not_mutate_store(tmp_path: Path) -> None:
    bundle = _write_bundle(tmp_path / "bundle", {"model/model.onnx": b"model"})
    artifact = _zip_bundle(bundle, tmp_path / "model-bundle.zip")
    database = tmp_path / "access-control.sqlite3"
    repository = SqliteAccessControlRepository(database)
    repository.put_identity(
        Identity("installer", IdentityKind.SERVICE, "Security installer", "platform")
    )
    store = tmp_path / "store"

    with pytest.raises(ModelBundleError, match="business authorization denied"):
        install_model_bundle(
            bundle,
            store,
            security_install_artifact=artifact,
            security_install_evidence=_evidence(artifact),
            access_control_database=database,
            security_install_subject="installer",
            actual_target_version="not-installed",
        )

    assert not store.exists()


def test_install_rejects_unpacked_payload_changed_after_archive_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _write_bundle(tmp_path / "bundle", {"model/model.onnx": b"model"})
    store = tmp_path / "store"
    _artifact, _database, kwargs = _install_kwargs(tmp_path, bundle)
    original = model_bundle_cli._verify_security_install_archive

    def verify_then_tamper(*args, **inner_kwargs):
        original(*args, **inner_kwargs)
        (bundle / "model/model.onnx").write_bytes(b"evil!")

    monkeypatch.setattr(model_bundle_cli, "_verify_security_install_archive", verify_then_tamper)

    with pytest.raises(ModelBundleError, match="changed during install staging"):
        install_model_bundle(bundle, store, **kwargs)

    destination = store / "fieldora-test-model" / "1.0.0"
    assert not destination.exists()


def test_install_rehashes_transfer_artifact_immediately_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _write_bundle(tmp_path / "bundle", {"model/model.onnx": b"model"})
    store = tmp_path / "store"
    artifact, _database, kwargs = _install_kwargs(tmp_path, bundle)
    original = model_bundle_cli._copy_verified_file
    tampered = False

    def copy_then_tamper(*args, **inner_kwargs):
        nonlocal tampered
        original(*args, **inner_kwargs)
        if not tampered:
            with artifact.open("ab") as stream:
                stream.write(b"tampered-after-first-acceptance")
            tampered = True

    monkeypatch.setattr(model_bundle_cli, "_copy_verified_file", copy_then_tamper)

    with pytest.raises(
        ModelBundleError,
        match="Security Install acceptance failed: artifact size mismatch",
    ):
        install_model_bundle(bundle, store, **kwargs)

    destination = store / "fieldora-test-model" / "1.0.0"
    assert not destination.exists()
