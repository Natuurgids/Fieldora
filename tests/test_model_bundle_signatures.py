from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from natureai_next.bootstrap.model_bundle_cli import ModelBundleError, verify_model_bundle


def _signed_bundle(tmp_path: Path) -> tuple[Path, Path]:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    model = bundle / "model.gguf"
    model.write_bytes(b"model-bytes")
    manifest = {
        "model_id": "signed-model",
        "version": "1.0.0",
        "source": "fieldora-bastion",
        "license_id": "test-license",
        "files": [
            {
                "path": "model.gguf",
                "sha256": hashlib.sha256(b"model-bytes").hexdigest(),
                "size_bytes": len(b"model-bytes"),
            }
        ],
    }
    manifest_bytes = json.dumps(manifest, separators=(",", ":")).encode()
    (bundle / "manifest.json").write_bytes(manifest_bytes)
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    public_der = public.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_id = hashlib.sha256(public_der).hexdigest()[:32]
    (bundle / "manifest.sig").write_text(
        json.dumps(
            {
                "algorithm": "ed25519",
                "key_id": key_id,
                "signature": base64.b64encode(private.sign(manifest_bytes)).decode(),
            }
        ),
        encoding="utf-8",
    )
    public_path = tmp_path / "trusted-public.pem"
    public_path.write_bytes(
        public.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return bundle, public_path


def test_verifies_bastion_signed_manifest(tmp_path: Path) -> None:
    bundle, public_path = _signed_bundle(tmp_path)

    verified = verify_model_bundle(
        bundle,
        trusted_signing_key=public_path,
        require_signature=True,
    )

    assert verified.signature_verified
    assert verified.signing_key_id
    assert verified.registry_record()["manifest_signature"] == "ed25519"


def test_required_signature_fails_closed_when_missing(tmp_path: Path) -> None:
    bundle, public_path = _signed_bundle(tmp_path)
    (bundle / "manifest.sig").unlink()

    with pytest.raises(ModelBundleError, match="manifest.sig is missing"):
        verify_model_bundle(
            bundle,
            trusted_signing_key=public_path,
            require_signature=True,
        )


def test_signature_detects_manifest_tampering(tmp_path: Path) -> None:
    bundle, public_path = _signed_bundle(tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["license_id"] = "tampered"
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ModelBundleError, match="signature verification failed"):
        verify_model_bundle(
            bundle,
            trusted_signing_key=public_path,
            require_signature=True,
        )
