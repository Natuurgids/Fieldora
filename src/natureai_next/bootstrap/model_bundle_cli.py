"""Verify and install offline Fieldora model bundles without executing bundle code."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_MODEL_EXTENSIONS = {".safetensors", ".onnx", ".gguf"}
_SUPPORT_EXTENSIONS = {
    ".json",
    ".txt",
    ".md",
    ".model",
    ".vocab",
    ".merges",
    ".yaml",
    ".yml",
}
_FORBIDDEN_EXTENSIONS = {
    ".py",
    ".pyc",
    ".pyo",
    ".pkl",
    ".pickle",
    ".pt",
    ".pth",
    ".bin",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bat",
    ".cmd",
    ".ps1",
    ".sh",
}
_DEFAULT_MAX_BYTES = 64 * 1024 * 1024 * 1024
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_MAX_SIGNATURE_BYTES = 16 * 1024
_MAX_MANIFEST_FILES = 10_000
_MAX_METADATA_TEXT = 2_048


class ModelBundleError(ValueError):
    """Raised when an offline model bundle violates the trusted import contract."""


@dataclass(frozen=True, slots=True)
class VerifiedModelBundle:
    model_id: str
    version: str
    source: str
    license_id: str
    files: tuple[dict[str, object], ...]
    total_bytes: int
    signature_verified: bool = False
    signing_key_id: str = ""

    @property
    def artifact_storage_id(self) -> str:
        return f"model:{self.model_id}:{self.version}"

    @property
    def registry_id(self) -> str:
        return f"{self.model_id}@{self.version}"

    def registry_record(self) -> dict[str, object]:
        """Return browser-safe governed metadata; never expose filesystem paths."""
        return {
            "id": self.registry_id,
            "model_id": self.model_id,
            "name": self.model_id,
            "version": self.version,
            "project_id": "platform",
            "provider_id": "fieldora-offline",
            "network": "offline",
            "enabled": True,
            "status": "installed",
            "artifact_storage_id": self.artifact_storage_id,
            "artifact_total_bytes": self.total_bytes,
            "artifact_files": list(self.files),
            "source": self.source,
            "license_id": self.license_id,
            "verification": "sha256-per-file",
            "manifest_signature": "ed25519" if self.signature_verified else "unsigned",
            "signing_key_id": self.signing_key_id,
        }


def _require_token(value: object, field: str) -> str:
    token = str(value or "").strip()
    if not token or token in {".", ".."} or "/" in token or "\\" in token:
        raise ModelBundleError(f"manifest {field} must be a non-empty path-safe token")
    if not all(character.isalnum() or character in "._-" for character in token):
        raise ModelBundleError(f"manifest {field} contains unsupported characters")
    return token


def _bounded_text(value: object, field: str, default: str) -> str:
    text = str(value or default).strip()
    if not text:
        text = default
    if len(text) > _MAX_METADATA_TEXT:
        raise ModelBundleError(f"manifest {field} is too long")
    return text


def _safe_relative_path(value: object) -> PurePosixPath:
    raw = str(value or "").strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ModelBundleError(f"unsafe bundle path: {raw!r}")
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_manifest_signature(
    bundle_dir: Path,
    manifest_bytes: bytes,
    trusted_signing_key: Path | None,
    require_signature: bool,
) -> tuple[bool, str]:
    signature_path = bundle_dir / "manifest.sig"
    has_signature = signature_path.is_file() and not signature_path.is_symlink()
    if not has_signature:
        if require_signature:
            raise ModelBundleError("signed manifest is required but manifest.sig is missing")
        return False, ""
    if trusted_signing_key is None:
        raise ModelBundleError("manifest.sig is present but no trusted signing key was provided")
    if trusted_signing_key.is_symlink() or not trusted_signing_key.is_file():
        raise ModelBundleError("trusted signing key must be a regular non-symlink file")
    try:
        if signature_path.stat().st_size > _MAX_SIGNATURE_BYTES:
            raise ModelBundleError("manifest.sig exceeds the configured size limit")
        envelope = json.loads(signature_path.read_text(encoding="utf-8"))
        if not isinstance(envelope, dict) or envelope.get("algorithm") != "ed25519":
            raise ModelBundleError("manifest.sig must use the ed25519 algorithm")
        signature = base64.b64decode(str(envelope.get("signature") or ""), validate=True)
        public_key = serialization.load_pem_public_key(trusted_signing_key.read_bytes())
    except ModelBundleError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise ModelBundleError("manifest signature or trusted signing key is invalid") from exc
    if not isinstance(public_key, Ed25519PublicKey):
        raise ModelBundleError("trusted signing key must be an Ed25519 public key")
    public_der = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_id = hashlib.sha256(public_der).hexdigest()[:32]
    envelope_key_id = str(envelope.get("key_id") or "").strip()
    if envelope_key_id and envelope_key_id != key_id:
        raise ModelBundleError("manifest signature key_id does not match trusted signing key")
    try:
        public_key.verify(signature, manifest_bytes)
    except InvalidSignature as exc:
        raise ModelBundleError("manifest signature verification failed") from exc
    return True, key_id


def verify_model_bundle(
    bundle_dir: Path,
    *,
    max_total_bytes: int = _DEFAULT_MAX_BYTES,
    trusted_signing_key: Path | None = None,
    require_signature: bool = False,
) -> VerifiedModelBundle:
    if bundle_dir.is_symlink():
        raise ModelBundleError("bundle root must not be a symlink")
    bundle_dir = bundle_dir.resolve()
    if not bundle_dir.is_dir():
        raise ModelBundleError("bundle root must be a directory")
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ModelBundleError("bundle must contain a regular manifest.json")
    try:
        if manifest_path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise ModelBundleError("manifest.json exceeds the configured size limit")
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
    except ModelBundleError:
        raise
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ModelBundleError("manifest.json is unreadable or invalid JSON") from exc
    if not isinstance(manifest, dict):
        raise ModelBundleError("manifest.json must contain an object")
    signature_verified, signing_key_id = _verify_manifest_signature(
        bundle_dir,
        manifest_bytes,
        trusted_signing_key,
        require_signature,
    )

    model_id = _require_token(manifest.get("model_id"), "model_id")
    version = _require_token(manifest.get("version"), "version")
    source = _bounded_text(manifest.get("source"), "source", "offline-bundle")
    license_id = _bounded_text(manifest.get("license_id"), "license_id", "unspecified")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ModelBundleError("manifest files must be a non-empty list")
    if len(entries) > _MAX_MANIFEST_FILES:
        raise ModelBundleError("manifest contains too many files")

    verified: list[dict[str, object]] = []
    seen: set[str] = set()
    total = 0
    model_artifacts = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ModelBundleError("manifest file entries must be objects")
        relative = _safe_relative_path(entry.get("path"))
        relative_text = relative.as_posix()
        if relative_text in seen:
            raise ModelBundleError(f"duplicate bundle path: {relative_text}")
        seen.add(relative_text)
        suffix = relative.suffix.lower()
        if suffix in _FORBIDDEN_EXTENSIONS or suffix not in _MODEL_EXTENSIONS | _SUPPORT_EXTENSIONS:
            raise ModelBundleError(f"unsupported or executable model bundle file: {relative_text}")
        if suffix in _MODEL_EXTENSIONS:
            model_artifacts += 1

        expected_hash = str(entry.get("sha256") or "").lower()
        if len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash):
            raise ModelBundleError(f"invalid SHA-256 for {relative_text}")
        try:
            expected_size = int(entry.get("size_bytes"))
        except (TypeError, ValueError) as exc:
            raise ModelBundleError(f"invalid size_bytes for {relative_text}") from exc
        if expected_size < 0:
            raise ModelBundleError(f"invalid size_bytes for {relative_text}")

        source_path = bundle_dir.joinpath(*relative.parts)
        if source_path.is_symlink() or not source_path.is_file():
            raise ModelBundleError(f"bundle file must be a regular non-symlink: {relative_text}")
        try:
            resolved = source_path.resolve(strict=True)
            resolved.relative_to(bundle_dir)
        except (OSError, ValueError) as exc:
            raise ModelBundleError(f"bundle file escapes bundle root: {relative_text}") from exc
        actual_size = source_path.stat().st_size
        if actual_size != expected_size:
            raise ModelBundleError(f"size mismatch for {relative_text}")
        total += actual_size
        if total > max_total_bytes:
            raise ModelBundleError("model bundle exceeds configured maximum total size")
        actual_hash = _file_sha256(source_path)
        if actual_hash != expected_hash:
            raise ModelBundleError(f"SHA-256 mismatch for {relative_text}")
        verified.append(
            {"path": relative_text, "sha256": actual_hash, "size_bytes": actual_size}
        )

    if model_artifacts == 0:
        raise ModelBundleError("bundle contains no supported model artifact")
    return VerifiedModelBundle(
        model_id=model_id,
        version=version,
        source=source,
        license_id=license_id,
        files=tuple(verified),
        total_bytes=total,
        signature_verified=signature_verified,
        signing_key_id=signing_key_id,
    )


def install_model_bundle(
    bundle_dir: Path,
    model_store: Path,
    *,
    max_total_bytes: int = _DEFAULT_MAX_BYTES,
    trusted_signing_key: Path | None = None,
    require_signature: bool = False,
) -> tuple[VerifiedModelBundle, Path]:
    verified = verify_model_bundle(
        bundle_dir,
        max_total_bytes=max_total_bytes,
        trusted_signing_key=trusted_signing_key,
        require_signature=require_signature,
    )
    model_store.mkdir(parents=True, exist_ok=True)
    destination = model_store / verified.model_id / verified.version
    if destination.exists():
        raise ModelBundleError(f"model version is already installed: {verified.artifact_storage_id}")
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".fieldora-model-", dir=parent))
    try:
        for entry in verified.files:
            relative = PurePosixPath(str(entry["path"]))
            source = bundle_dir.resolve().joinpath(*relative.parts)
            target = temp_root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target, follow_symlinks=False)
        (temp_root / "FIELDORA-INSTALL.json").write_text(
            json.dumps(verified.registry_record(), ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
            encoding="utf-8",
        )
        os.replace(temp_root, destination)
    except BaseException:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    return verified, destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fieldora-model-bundle",
        description="Verify or install an offline Fieldora model bundle.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "install"):
        command = sub.add_parser(name)
        command.add_argument("bundle", type=Path)
        command.add_argument("--max-bytes", type=int, default=_DEFAULT_MAX_BYTES)
        command.add_argument("--trusted-signing-key", type=Path)
        command.add_argument("--require-signature", action="store_true")
        if name == "install":
            command.add_argument("--store", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        kwargs = {
            "max_total_bytes": args.max_bytes,
            "trusted_signing_key": args.trusted_signing_key,
            "require_signature": args.require_signature,
        }
        if args.command == "verify":
            verified = verify_model_bundle(args.bundle, **kwargs)
            output = {
                "model_id": verified.model_id,
                "version": verified.version,
                "total_bytes": verified.total_bytes,
                "verification": "sha256-per-file",
                "manifest_signature": (
                    "ed25519" if verified.signature_verified else "unsigned"
                ),
                "signing_key_id": verified.signing_key_id,
            }
        else:
            verified, _destination = install_model_bundle(
                args.bundle,
                args.store,
                **kwargs,
            )
            output = verified.registry_record()
    except ModelBundleError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        return 2
    print(json.dumps({"ok": True, **output}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
