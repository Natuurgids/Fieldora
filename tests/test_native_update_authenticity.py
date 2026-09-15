from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from natureai_next.application.update_trust import (
    UpdateAuthenticityError,
    canonical_json_bytes,
    canonical_sha256,
)
from natureai_next.application.updates import OfflineUpdateService


def _write_signed_update(tmp_path: Path, *, signing_key: Ed25519PrivateKey | None = None) -> tuple[Path, Path]:
    source = tmp_path / "media"
    source.mkdir()
    package = source / "fieldora-5.5.0.bin"
    package.write_bytes(b"fieldora authenticated update")
    evidence = {"protocol_version": 1, "release_id": "release-5.5.0", "package_id": package.name}
    payload = {
        "format": "natureai-next.update-index", "format_version": 2, "product": "Fieldora",
        "channel": "stable", "version": "5.5.0", "minimum_supported_version": "5.4.0",
        "package": package.name, "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "size": package.stat().st_size, "release_id": "release-5.5.0", "release_digest": "a" * 64,
        "security_install_sha256": canonical_sha256(evidence), "security_install": evidence,
    }
    key = signing_key or Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    trust = tmp_path / "update-trust-anchors.json"
    trust.write_text(json.dumps({"format": "natureai-next.update-trust-anchors", "format_version": 1, "keys": {"release-2026": base64.b64encode(public).decode("ascii")}}), encoding="utf-8")
    signature = key.sign(canonical_json_bytes(payload))
    (source / "update-index.json").write_text(json.dumps({"format": "natureai-next.signed-update", "format_version": 1, "key_id": "release-2026", "signed": payload, "signature": base64.b64encode(signature).decode("ascii")}), encoding="utf-8")
    return source, trust


def _resign(source: Path, trust: Path, mutate) -> None:
    envelope = json.loads((source / "update-index.json").read_text(encoding="utf-8"))
    mutate(envelope["signed"])
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    trust.write_text(json.dumps({"format": "natureai-next.update-trust-anchors", "format_version": 1, "keys": {"release-2026": base64.b64encode(public).decode("ascii")}}), encoding="utf-8")
    envelope["signature"] = base64.b64encode(key.sign(canonical_json_bytes(envelope["signed"]))).decode("ascii")
    (source / "update-index.json").write_text(json.dumps(envelope), encoding="utf-8")


def test_valid_signed_native_update_is_accepted(tmp_path: Path) -> None:
    source, trust = _write_signed_update(tmp_path)
    candidate = OfflineUpdateService(trust_anchor_path=trust, current_version="5.4.0").check(source)
    assert candidate is not None
    assert candidate.version == "5.5.0"
    assert candidate.signer_key_id == "release-2026"


def test_unsigned_update_index_is_rejected(tmp_path: Path) -> None:
    source, trust = _write_signed_update(tmp_path)
    envelope = json.loads((source / "update-index.json").read_text(encoding="utf-8"))
    (source / "update-index.json").write_text(json.dumps(envelope["signed"]), encoding="utf-8")
    with pytest.raises(UpdateAuthenticityError, match="unsigned"):
        OfflineUpdateService(trust_anchor_path=trust, current_version="5.4.0").check(source)


def test_tampered_version_and_minimum_are_rejected_before_rollback_logic(tmp_path: Path) -> None:
    for field, value in (("version", "9.9.9"), ("minimum_supported_version", "9.9.9")):
        case = tmp_path / field
        case.mkdir()
        source, trust = _write_signed_update(case)
        envelope = json.loads((source / "update-index.json").read_text(encoding="utf-8"))
        envelope["signed"][field] = value
        (source / "update-index.json").write_text(json.dumps(envelope), encoding="utf-8")
        with pytest.raises(UpdateAuthenticityError, match="signature verification failed"):
            OfflineUpdateService(trust_anchor_path=trust, current_version="5.4.0").check(source)


def test_untrusted_signer_is_rejected(tmp_path: Path) -> None:
    source, trust = _write_signed_update(tmp_path)
    other = Ed25519PrivateKey.generate().public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    trust.write_text(json.dumps({"format": "natureai-next.update-trust-anchors", "format_version": 1, "keys": {"other": base64.b64encode(other).decode("ascii")}}), encoding="utf-8")
    with pytest.raises(UpdateAuthenticityError, match="untrusted key"):
        OfflineUpdateService(trust_anchor_path=trust, current_version="5.4.0").check(source)


def test_package_integrity_mismatch_is_rejected(tmp_path: Path) -> None:
    source, trust = _write_signed_update(tmp_path)
    package = source / "fieldora-5.5.0.bin"
    package.write_bytes(package.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="checksum"):
        OfflineUpdateService(trust_anchor_path=trust, current_version="5.4.0").check(source)


def test_signed_package_size_mismatch_is_rejected(tmp_path: Path) -> None:
    source, trust = _write_signed_update(tmp_path)
    _resign(source, trust, lambda payload: payload.__setitem__("size", payload["size"] + 1))
    with pytest.raises(ValueError, match="size"):
        OfflineUpdateService(trust_anchor_path=trust, current_version="5.4.0").check(source)


@pytest.mark.parametrize("bad_size", [True, "27", -1])
def test_malformed_signed_package_size_is_rejected(tmp_path: Path, bad_size: object) -> None:
    source, trust = _write_signed_update(tmp_path)
    _resign(source, trust, lambda payload: payload.__setitem__("size", bad_size))
    with pytest.raises(UpdateAuthenticityError, match="package size"):
        OfflineUpdateService(trust_anchor_path=trust, current_version="5.4.0").check(source)


def test_signed_package_path_traversal_is_rejected(tmp_path: Path) -> None:
    source, trust = _write_signed_update(tmp_path)
    _resign(source, trust, lambda payload: payload.__setitem__("package", "../fieldora-5.5.0.bin"))
    with pytest.raises(UpdateAuthenticityError, match="package basename"):
        OfflineUpdateService(trust_anchor_path=trust, current_version="5.4.0").check(source)


def test_security_install_evidence_digest_mismatch_is_rejected(tmp_path: Path) -> None:
    source, trust = _write_signed_update(tmp_path)
    _resign(source, trust, lambda payload: payload["security_install"].__setitem__("release_id", "tampered-evidence"))
    with pytest.raises(UpdateAuthenticityError, match="not bound"):
        OfflineUpdateService(trust_anchor_path=trust, current_version="5.4.0").check(source)
