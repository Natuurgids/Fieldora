"""Ed25519 identities and detached attestations for governed exports."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


class ExportSigningIdentity:
    algorithm = "Ed25519"

    def __init__(self, key_id: str, private_key: Ed25519PrivateKey) -> None:
        self.key_id = key_id
        self._private_key = private_key

    @classmethod
    def generate(
        cls, key_id: str, private_key_path: Path, trusted_keys_path: Path
    ) -> "ExportSigningIdentity":
        key_id = key_id.strip()
        if not key_id or private_key_path.exists() or trusted_keys_path.exists():
            raise ValueError("signing identity already exists or has an invalid key ID")
        private_key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        private_temporary = private_key_path.with_suffix(".pem.partial")
        trust_temporary = trusted_keys_path.with_suffix(".json.partial")
        try:
            private_temporary.write_bytes(
                key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            )
            public = key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            trust_temporary.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "algorithm": cls.algorithm,
                        "keys": {key_id: base64.b64encode(public).decode("ascii")},
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            private_temporary.replace(private_key_path)
            trust_temporary.replace(trusted_keys_path)
            try:
                os.chmod(private_key_path, 0o600)
            except OSError:
                pass
        except BaseException:
            private_temporary.unlink(missing_ok=True)
            trust_temporary.unlink(missing_ok=True)
            private_key_path.unlink(missing_ok=True)
            trusted_keys_path.unlink(missing_ok=True)
            raise
        return cls(key_id, key)

    @classmethod
    def load(cls, key_id: str, private_key_path: Path) -> "ExportSigningIdentity":
        value = serialization.load_pem_private_key(
            private_key_path.read_bytes(), password=None
        )
        if not isinstance(value, Ed25519PrivateKey):
            raise ValueError("an Ed25519 export signing key is required")
        return cls(key_id, value)

    def attest(self, package_sha256: str) -> dict:
        unsigned = {
            "schema_version": 1,
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "package_sha256": package_sha256,
        }
        return {
            **unsigned,
            "signature": base64.b64encode(
                self._private_key.sign(_canonical(unsigned))
            ).decode("ascii"),
        }


def verify_export_attestation(
    package_path: Path, attestation: dict, trusted_keys_path: Path
) -> str:
    trusted = json.loads(trusted_keys_path.read_text(encoding="utf-8"))
    if (
        attestation.get("schema_version") != 1
        or attestation.get("algorithm") != "Ed25519"
        or trusted.get("schema_version") != 1
        or trusted.get("algorithm") != "Ed25519"
    ):
        raise ValueError("unsupported export attestation")
    digest_builder = hashlib.sha256()
    with package_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest_builder.update(chunk)
    digest = digest_builder.hexdigest()
    if digest != attestation.get("package_sha256"):
        raise ValueError("export package checksum does not match its attestation")
    key_id = str(attestation.get("key_id", ""))
    try:
        public = base64.b64decode(trusted["keys"][key_id], validate=True)
        signature = base64.b64decode(attestation["signature"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("export attestation uses an untrusted key") from exc
    unsigned = dict(attestation)
    unsigned.pop("signature", None)
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(
            signature, _canonical(unsigned)
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("invalid export attestation signature") from exc
    return digest
