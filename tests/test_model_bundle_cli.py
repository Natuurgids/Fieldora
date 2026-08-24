from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from natureai_next.bootstrap.model_bundle_cli import (
    ModelBundleError,
    install_model_bundle,
    verify_model_bundle,
)


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


def test_install_is_versioned_atomic_and_writes_registry_receipt(tmp_path: Path) -> None:
    bundle = _write_bundle(
        tmp_path / "bundle",
        {"model/model.safetensors": b"model", "model/config.json": b"{}"},
    )
    store = tmp_path / "store"

    verified, destination = install_model_bundle(bundle, store)

    assert destination == store / "fieldora-test-model" / "1.0.0"
    assert (destination / "model/model.safetensors").read_bytes() == b"model"
    receipt = json.loads((destination / "FIELDORA-INSTALL.json").read_text(encoding="utf-8"))
    assert receipt["id"] == verified.model_id
    assert receipt["provider_id"] == "fieldora-offline"
    assert receipt["network"] == "offline"
    assert receipt["verification"] == "sha256-per-file"
    assert receipt["artifact_total_bytes"] == verified.total_bytes

    with pytest.raises(ModelBundleError, match="already installed"):
        install_model_bundle(bundle, store)
