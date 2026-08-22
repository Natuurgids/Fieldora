"""Recipient-key encryption for governed project export packages."""

from __future__ import annotations

import base64
import json
import os
import struct
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_MAGIC = b"FIELDORA-ENC-1\n"
_TAG_SIZE = 16


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def generate_recipient_identity(
    key_id: str, private_key_path: Path, public_key_path: Path
) -> None:
    key_id = key_id.strip()
    if not key_id or private_key_path.exists() or public_key_path.exists():
        raise ValueError("recipient identity already exists or has an invalid key ID")
    private_key_path.parent.mkdir(parents=True, exist_ok=True)
    private = X25519PrivateKey.generate()
    private_temporary = private_key_path.with_suffix(".pem.partial")
    public_temporary = public_key_path.with_suffix(".json.partial")
    try:
        private_temporary.write_bytes(
            private.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        public = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        public_temporary.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "algorithm": "X25519",
                    "key_id": key_id,
                    "public_key": base64.b64encode(public).decode("ascii"),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        private_temporary.replace(private_key_path)
        public_temporary.replace(public_key_path)
        try:
            os.chmod(private_key_path, 0o600)
        except OSError:
            pass
    except BaseException:
        private_temporary.unlink(missing_ok=True)
        public_temporary.unlink(missing_ok=True)
        private_key_path.unlink(missing_ok=True)
        public_key_path.unlink(missing_ok=True)
        raise


def load_recipient_public_key(value: dict) -> tuple[str, X25519PublicKey]:
    if value.get("schema_version") != 1 or value.get("algorithm") != "X25519":
        raise ValueError("unsupported recipient public key")
    key_id = str(value.get("key_id", "")).strip()
    try:
        raw = base64.b64decode(value["public_key"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid recipient public key") from exc
    if not key_id or len(raw) != 32:
        raise ValueError("invalid recipient public key")
    return key_id, X25519PublicKey.from_public_bytes(raw)


def _content_key(shared: bytes, key_id: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=f"fieldora.project-export.v1:{key_id}".encode(),
    ).derive(shared)


def encrypt_project_export(
    source: Path, destination: Path, recipient_public: dict
) -> None:
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError("encrypted export destination must be new")
    key_id, recipient = load_recipient_public_key(recipient_public)
    ephemeral = X25519PrivateKey.generate()
    nonce = os.urandom(12)
    header = {
        "schema_version": 1,
        "key_agreement": "X25519-HKDF-SHA256",
        "cipher": "AES-256-GCM",
        "recipient_key_id": key_id,
        "ephemeral_public_key": base64.b64encode(
            ephemeral.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        ).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
    }
    header_bytes = _canonical(header)
    encryptor = Cipher(
        algorithms.AES(_content_key(ephemeral.exchange(recipient), key_id)),
        modes.GCM(nonce),
    ).encryptor()
    encryptor.authenticate_additional_data(header_bytes)
    temporary = destination.with_suffix(destination.suffix + ".encrypting")
    try:
        with source.open("rb") as incoming, temporary.open("wb") as outgoing:
            outgoing.write(_MAGIC)
            outgoing.write(struct.pack(">I", len(header_bytes)))
            outgoing.write(header_bytes)
            for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                outgoing.write(encryptor.update(chunk))
            outgoing.write(encryptor.finalize())
            outgoing.write(encryptor.tag)
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise


def decrypt_project_export(
    source: Path, destination: Path, private_key_path: Path
) -> str:
    if source.resolve() == destination.resolve() or destination.exists():
        raise ValueError("decrypted export destination must be new")
    private = serialization.load_pem_private_key(
        private_key_path.read_bytes(), password=None
    )
    if not isinstance(private, X25519PrivateKey):
        raise ValueError("an X25519 recipient private key is required")
    temporary = destination.with_suffix(destination.suffix + ".decrypting")
    try:
        with source.open("rb") as incoming:
            if incoming.read(len(_MAGIC)) != _MAGIC:
                raise ValueError("unsupported encrypted project export")
            header_size_bytes = incoming.read(4)
            if len(header_size_bytes) != 4:
                raise ValueError("truncated encrypted project export")
            header_size = struct.unpack(">I", header_size_bytes)[0]
            if header_size > 16_384:
                raise ValueError("encrypted project export header is too large")
            header_bytes = incoming.read(header_size)
            header = json.loads(header_bytes.decode("utf-8"))
            key_id = str(header["recipient_key_id"])
            ephemeral = base64.b64decode(
                header["ephemeral_public_key"], validate=True
            )
            nonce = base64.b64decode(header["nonce"], validate=True)
            if (
                header.get("schema_version") != 1
                or header.get("key_agreement") != "X25519-HKDF-SHA256"
                or header.get("cipher") != "AES-256-GCM"
                or len(ephemeral) != 32
                or len(nonce) != 12
            ):
                raise ValueError("unsupported encrypted project export")
            ciphertext_start = incoming.tell()
            total_size = source.stat().st_size
            ciphertext_size = total_size - ciphertext_start - _TAG_SIZE
            if ciphertext_size < 0:
                raise ValueError("truncated encrypted project export")
            incoming.seek(total_size - _TAG_SIZE)
            tag = incoming.read(_TAG_SIZE)
            incoming.seek(ciphertext_start)
            decryptor = Cipher(
                algorithms.AES(
                    _content_key(
                        private.exchange(X25519PublicKey.from_public_bytes(ephemeral)),
                        key_id,
                    )
                ),
                modes.GCM(nonce, tag),
            ).decryptor()
            decryptor.authenticate_additional_data(header_bytes)
            remaining = ciphertext_size
            with temporary.open("wb") as outgoing:
                while remaining:
                    chunk = incoming.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("truncated encrypted project export")
                    remaining -= len(chunk)
                    outgoing.write(decryptor.update(chunk))
                outgoing.write(decryptor.finalize())
        temporary.replace(destination)
        return key_id
    except (InvalidTag, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise ValueError("encrypted project export authentication failed") from exc
