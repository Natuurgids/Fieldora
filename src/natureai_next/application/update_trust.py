"""Cryptographic trust boundary for native update release manifests."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SIGNED_UPDATE_FORMAT = "natureai-next.signed-update"
SIGNED_UPDATE_FORMAT_VERSION = 1
UPDATE_INDEX_FORMAT = "natureai-next.update-index"
UPDATE_INDEX_FORMAT_VERSION = 2
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class UpdateAuthenticityError(ValueError):
    """Raised when native update metadata cannot be authenticated."""


@dataclass(frozen=True, slots=True)
class VerifiedUpdateManifest:
    payload: dict[str, object]
    key_id: str


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise UpdateAuthenticityError(f"invalid signed native update {field}")
    return value


def _require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise UpdateAuthenticityError(f"invalid signed native update {field}")
    return value.casefold()


def load_update_trust_anchors(path: Path) -> dict[str, Ed25519PublicKey]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UpdateAuthenticityError("native update trust anchors are unavailable") from exc
    if not isinstance(document, Mapping) or document.get("format") != "natureai-next.update-trust-anchors":
        raise UpdateAuthenticityError("invalid native update trust-anchor format")
    if document.get("format_version") != 1 or not isinstance(document.get("keys"), Mapping):
        raise UpdateAuthenticityError("invalid native update trust-anchor format")
    anchors: dict[str, Ed25519PublicKey] = {}
    for raw_key_id, raw_key in document["keys"].items():
        key_id = _require_token(raw_key_id, "trust-anchor key id")
        if not isinstance(raw_key, str):
            raise UpdateAuthenticityError("invalid native update trust anchor")
        try:
            key_bytes = base64.b64decode(raw_key, validate=True)
            anchors[key_id] = Ed25519PublicKey.from_public_bytes(key_bytes)
        except (ValueError, binascii.Error) as exc:
            raise UpdateAuthenticityError("invalid native update trust anchor") from exc
    if not anchors:
        raise UpdateAuthenticityError("no native update trust anchors are configured")
    return anchors


def verify_signed_update_index(index_path: Path, trust_anchor_path: Path) -> VerifiedUpdateManifest:
    try:
        envelope = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UpdateAuthenticityError("native update index is unreadable") from exc
    if not isinstance(envelope, Mapping):
        raise UpdateAuthenticityError("native update index must be a signed object")
    if envelope.get("format") != SIGNED_UPDATE_FORMAT or envelope.get("format_version") != SIGNED_UPDATE_FORMAT_VERSION:
        raise UpdateAuthenticityError("unsigned or unsupported native update index")
    key_id = _require_token(envelope.get("key_id"), "signer key id")
    signature_text = envelope.get("signature")
    payload = envelope.get("signed")
    if not isinstance(signature_text, str) or not isinstance(payload, Mapping):
        raise UpdateAuthenticityError("malformed native update signature envelope")
    public_key = load_update_trust_anchors(trust_anchor_path).get(key_id)
    if public_key is None:
        raise UpdateAuthenticityError("native update index was signed by an untrusted key")
    try:
        signature = base64.b64decode(signature_text, validate=True)
        public_key.verify(signature, canonical_json_bytes(payload))
    except (InvalidSignature, ValueError, binascii.Error) as exc:
        raise UpdateAuthenticityError("native update index signature verification failed") from exc

    verified = dict(payload)
    required = {"format", "format_version", "product", "channel", "version", "minimum_supported_version", "package", "sha256", "size", "release_id", "release_digest", "security_install_sha256", "security_install"}
    if required.difference(verified):
        raise UpdateAuthenticityError("signed native update metadata is incomplete")
    if verified.get("format") != UPDATE_INDEX_FORMAT or verified.get("format_version") != UPDATE_INDEX_FORMAT_VERSION:
        raise UpdateAuthenticityError("unsupported signed native update metadata format")
    for field in ("product", "channel", "version", "minimum_supported_version", "release_id"):
        _require_token(verified.get(field), field)
    package = verified.get("package")
    if not isinstance(package, str) or not package or Path(package).name != package:
        raise UpdateAuthenticityError("invalid signed native update package basename")
    _require_sha256(verified.get("sha256"), "package sha256")
    _require_sha256(verified.get("release_digest"), "release digest")
    evidence_digest = _require_sha256(verified.get("security_install_sha256"), "Security Install evidence digest")
    size = verified.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise UpdateAuthenticityError("invalid signed native update package size")
    evidence = verified.get("security_install")
    if not isinstance(evidence, Mapping):
        raise UpdateAuthenticityError("signed Security Install evidence is missing")
    if evidence_digest != canonical_sha256(evidence):
        raise UpdateAuthenticityError("Security Install evidence is not bound by the signed update metadata")
    return VerifiedUpdateManifest(payload=verified, key_id=key_id)
