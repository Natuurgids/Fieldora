"""Create a canonical Ed25519-signed Fieldora native update index.

The private key is supplied at invocation time and is never written to the release output.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_private_key

from natureai_next.application.update_trust import (
    SIGNED_UPDATE_FORMAT,
    SIGNED_UPDATE_FORMAT_VERSION,
    UPDATE_INDEX_FORMAT,
    UPDATE_INDEX_FORMAT_VERSION,
    canonical_json_bytes,
    canonical_sha256,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-key", required=True, type=Path, help="PEM Ed25519 private key")
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--security-install", required=True, type=Path, help="Security Install evidence JSON")
    parser.add_argument("--version", required=True)
    parser.add_argument("--minimum-supported-version", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--release-digest", required=True)
    parser.add_argument("--product", default="Fieldora")
    parser.add_argument("--channel", default="stable")
    parser.add_argument("--release-notes", default="")
    parser.add_argument("--output", type=Path, default=Path("update-index.json"))
    args = parser.parse_args()

    package = args.package.resolve()
    if not package.is_file() or package.is_symlink():
        parser.error("--package must be a regular non-symlink file")
    evidence = json.loads(args.security_install.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict):
        parser.error("--security-install must contain a JSON object")

    payload = {
        "format": UPDATE_INDEX_FORMAT,
        "format_version": UPDATE_INDEX_FORMAT_VERSION,
        "product": args.product,
        "channel": args.channel,
        "version": args.version,
        "minimum_supported_version": args.minimum_supported_version,
        "package": package.name,
        "sha256": _sha256(package),
        "size": package.stat().st_size,
        "release_id": args.release_id,
        "release_digest": args.release_digest.casefold(),
        "security_install_sha256": canonical_sha256(evidence),
        "security_install": evidence,
    }
    if args.release_notes:
        payload["release_notes"] = args.release_notes

    private_key = load_pem_private_key(args.private_key.read_bytes(), password=None)
    if private_key.__class__.__name__ != "Ed25519PrivateKey":
        parser.error("--private-key must contain an Ed25519 private key")
    signature = private_key.sign(canonical_json_bytes(payload))
    envelope = {
        "format": SIGNED_UPDATE_FORMAT,
        "format_version": SIGNED_UPDATE_FORMAT_VERSION,
        "key_id": args.key_id,
        "signature": base64.b64encode(signature).decode("ascii"),
        "signed": payload,
    }
    args.output.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
