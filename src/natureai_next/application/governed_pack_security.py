"""Encrypted, signed, expiring, and revocable governed-pack lifecycle."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Protocol

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _canonical(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


class ContentKeyVault(Protocol):
    def put(self, key_ref: str, key: bytes) -> None: ...
    def get(self, key_ref: str) -> bytes: ...
    def delete(self, key_ref: str) -> None: ...


class GovernedPackEnvelope:
    FORMAT = "fieldora.governed-pack-envelope"
    VERSION = 1

    def seal(
        self, payload: bytes, *, pack_id: str, expires_at_utc: str,
        signing_key_id: str, content_key: bytes, signing_key: Ed25519PrivateKey,
    ) -> bytes:
        if len(content_key) != 32:
            raise ValueError("governed pack content key must be 256 bits")
        header = {
            "format": self.FORMAT, "version": self.VERSION, "pack_id": pack_id,
            "expires_at_utc": expires_at_utc, "signing_key_id": signing_key_id,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
        header_bytes = _canonical(header)
        nonce = os.urandom(12)
        ciphertext = AESGCM(content_key).encrypt(nonce, payload, header_bytes)
        signature = signing_key.sign(header_bytes + nonce + ciphertext)
        return _canonical({
            "header": header,
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
            "signature": base64.b64encode(signature).decode(),
        })

    def open(
        self, envelope: bytes, *, content_key: bytes,
        verification_key: Ed25519PublicKey, at_utc: str,
    ) -> tuple[dict, bytes]:
        document = json.loads(envelope)
        header = document.get("header")
        if (
            not isinstance(header, dict)
            or header.get("format") != self.FORMAT
            or header.get("version") != self.VERSION
        ):
            raise ValueError("unsupported governed pack envelope")
        if at_utc >= str(header.get("expires_at_utc", "")):
            raise PermissionError("governed pack has expired")
        header_bytes = _canonical(header)
        nonce = base64.b64decode(document["nonce"], validate=True)
        ciphertext = base64.b64decode(document["ciphertext"], validate=True)
        signature = base64.b64decode(document["signature"], validate=True)
        verification_key.verify(signature, header_bytes + nonce + ciphertext)
        payload = AESGCM(content_key).decrypt(nonce, ciphertext, header_bytes)
        if hashlib.sha256(payload).hexdigest() != header["payload_sha256"]:
            raise ValueError("governed pack payload checksum mismatch")
        return header, payload


class SecureGovernedPackManager:
    def __init__(self, root: Path, registry, key_vault: ContentKeyVault) -> None:
        self._root = root
        self._registry = registry
        self._keys = key_vault
        self._codec = GovernedPackEnvelope()

    def install(
        self, envelope: bytes, *, pack_id: str, enrollment_id: str, key_ref: str,
        content_key: bytes, expires_at_utc: str, signing_key_id: str,
    ) -> Path:
        target = self._root / enrollment_id / f"{pack_id}.fieldora-pack.enc"
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_suffix(".pending")
        staging.write_bytes(envelope)
        os.replace(staging, target)
        self._keys.put(key_ref, content_key)
        self._registry.put_pack_security(
            pack_id, enrollment_id, str(target), key_ref, expires_at_utc, signing_key_id
        )
        return target

    def open(self, pack_id: str, *, verification_key: Ed25519PublicKey, at_utc: str) -> bytes:
        record = self._registry.pack_security(pack_id)
        if record is None or record["state"] != "active":
            raise PermissionError("governed pack is unavailable or revoked")
        _header, payload = self._codec.open(
            Path(record["envelope_path"]).read_bytes(),
            content_key=self._keys.get(record["key_ref"]),
            verification_key=verification_key, at_utc=at_utc,
        )
        return payload

    def revoke(self, pack_id: str) -> None:
        record = self._registry.pack_security(pack_id)
        if record is None:
            return
        self._registry.set_pack_security_state(pack_id, "revoked")
        self._keys.delete(record["key_ref"])
        path = Path(record["envelope_path"])
        if path.exists():
            path.unlink()
        parent = path.parent
        if parent.exists() and not any(parent.iterdir()):
            shutil.rmtree(parent)

