from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from natureai_next.bootstrap.model_bundle_cli import ModelBundleError, verify_model_bundle


def _bundle(
    tmp_path: Path,
    *,
    result: str = "clean",
    file_count: int = 1,
    signed: bool = True,
) -> tuple[Path, Path]:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    payload = b"model-bytes"
    (bundle / "model.gguf").write_bytes(payload)
    manifest = {
        "model_id": "scan-model",
        "version": "1.0.0",
        "source": "fieldora-bastion",
        "license_id": "test-license",
        "files": [
            {
                "path": "model.gguf",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }
        ],
        "inspection": {
            "malware_scan": {
                "result": result,
                "scanner": "clamav",
                "scanner_version": "1.4.0",
                "definitions": "daily-12345",
                "scanned_at": "2026-08-24T17:00:00Z",
                "file_count": file_count,
            }
        },
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    (bundle / "manifest.json").write_bytes(manifest_bytes)
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    public_der = public.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_id = hashlib.sha256(public_der).hexdigest()[:32]
    if signed:
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


def test_requires_and_preserves_signed_clean_scan(tmp_path: Path) -> None:
    bundle, key = _bundle(tmp_path)

    verified = verify_model_bundle(
        bundle,
        trusted_signing_key=key,
        require_clean_scan=True,
    )

    assert verified.signature_verified
    assert verified.malware_scan == {
        "result": "clean",
        "scanner": "clamav",
        "scanner_version": "1.4.0",
        "definitions": "daily-12345",
        "scanned_at": "2026-08-24T17:00:00Z",
        "file_count": 1,
    }
    assert verified.registry_record()["malware_scan"] == verified.malware_scan


def test_rejects_unsigned_scan_claim_even_when_clean(tmp_path: Path) -> None:
    bundle, _key = _bundle(tmp_path, signed=False)

    with pytest.raises(ModelBundleError, match="manifest.sig is missing"):
        verify_model_bundle(bundle, require_clean_scan=True)


def test_rejects_non_clean_or_wrong_count_scan_attestation(tmp_path: Path) -> None:
    infected, infected_key = _bundle(tmp_path / "infected", result="infected")
    with pytest.raises(ModelBundleError, match="not clean"):
        verify_model_bundle(
            infected,
            trusted_signing_key=infected_key,
            require_clean_scan=True,
        )

    wrong_count, wrong_count_key = _bundle(tmp_path / "count", file_count=2)
    with pytest.raises(ModelBundleError, match="file_count does not match"):
        verify_model_bundle(
            wrong_count,
            trusted_signing_key=wrong_count_key,
            require_clean_scan=True,
        )
