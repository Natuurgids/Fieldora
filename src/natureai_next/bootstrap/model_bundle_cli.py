"""Verify and install offline Fieldora model bundles without executing bundle code."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from natureai_next.application.security_install import require_security_install
from natureai_next.domain.security_install import (
    AuthenticatedReleaseContext,
    SecurityInstallAcceptanceError,
)

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
    malware_scan: dict[str, object] | None = None

    @property
    def artifact_storage_id(self) -> str:
        return f"model:{self.model_id}:{self.version}"

    @property
    def registry_id(self) -> str:
        return f"{self.model_id}@{self.version}"

    def registry_record(self) -> dict[str, object]:
        """Return browser-safe governed metadata; never expose filesystem paths."""
        record: dict[str, object] = {
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
        if self.malware_scan is not None:
            record["malware_scan"] = dict(self.malware_scan)
        return record


def _require_token(value: object, field: str) -> str:
    token = str(value or "").strip()
    if not token or token in {".", ".."} or "/" in token or "\\" in token:
        raise ModelBundleError(f"manifest {field} must be a non-empty path-safe token")
    if not all(character.isalnum() or character in "._-" for character in token):
        raise ModelBundleError(f"manifest {field} contains unsupported characters")
    return token


def _bounded_text(value: object, field: str, default: str) -> str:
    text = str(value or default).strip() or default
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


def _payload_tree_sha256(entries: tuple[dict[str, object], ...] | list[dict[str, object]]) -> str:
    """Digest canonical path/size/content-hash tuples used by Bastion scanning."""
    digest = hashlib.sha256()
    normalized = sorted(
        (
            str(entry["path"]),
            int(entry["size_bytes"]),
            str(entry["sha256"]),
        )
        for entry in entries
    )
    for path, size, sha256 in normalized:
        digest.update(f"{path}\0{size}\0{sha256}\n".encode())
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


def _malware_scan_attestation(
    manifest: dict[str, object],
    verified_files: tuple[dict[str, object], ...],
    *,
    signature_verified: bool,
    require_clean_scan: bool,
) -> dict[str, object] | None:
    inspection = manifest.get("inspection")
    if inspection is None:
        if require_clean_scan:
            raise ModelBundleError("signed clean malware scan attestation is required")
        return None
    if not isinstance(inspection, dict):
        raise ModelBundleError("manifest inspection must be an object")
    scan = inspection.get("malware_scan")
    if scan is None:
        if require_clean_scan:
            raise ModelBundleError("signed clean malware scan attestation is required")
        return None
    if not isinstance(scan, dict):
        raise ModelBundleError("manifest malware_scan must be an object")
    if not signature_verified:
        raise ModelBundleError("malware scan attestation requires a verified signed manifest")
    if str(scan.get("result") or "").strip().lower() != "clean":
        raise ModelBundleError("malware scan attestation is not clean")
    try:
        scanned_files = int(scan.get("file_count"))
    except (TypeError, ValueError) as exc:
        raise ModelBundleError("malware scan file_count is invalid") from exc
    if scanned_files != len(verified_files):
        raise ModelBundleError("malware scan file_count does not match manifest payload")
    payload_sha256 = str(scan.get("payload_sha256") or "").strip().lower()
    if len(payload_sha256) != 64 or any(c not in "0123456789abcdef" for c in payload_sha256):
        raise ModelBundleError("malware scan payload_sha256 is invalid")
    if payload_sha256 != _payload_tree_sha256(verified_files):
        raise ModelBundleError("malware scan payload digest does not match manifest payload")
    return {
        "result": "clean",
        "scanner": _bounded_text(scan.get("scanner"), "scanner", "unknown"),
        "scanner_version": _bounded_text(
            scan.get("scanner_version"), "scanner_version", "unknown"
        ),
        "definitions": _bounded_text(scan.get("definitions"), "definitions", "unknown"),
        "scanned_at": _bounded_text(scan.get("scanned_at"), "scanned_at", "unknown"),
        "file_count": scanned_files,
        "payload_sha256": payload_sha256,
    }


def verify_model_bundle(
    bundle_dir: Path,
    *,
    max_total_bytes: int = _DEFAULT_MAX_BYTES,
    trusted_signing_key: Path | None = None,
    require_signature: bool = False,
    require_clean_scan: bool = False,
) -> VerifiedModelBundle:
    if max_total_bytes <= 0:
        raise ModelBundleError("maximum bundle size must be positive")
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
        require_signature or require_clean_scan,
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
    verified_files = tuple(verified)
    malware_scan = _malware_scan_attestation(
        manifest,
        verified_files,
        signature_verified=signature_verified,
        require_clean_scan=require_clean_scan,
    )
    return VerifiedModelBundle(
        model_id=model_id,
        version=version,
        source=source,
        license_id=license_id,
        files=verified_files,
        total_bytes=total,
        signature_verified=signature_verified,
        signing_key_id=signing_key_id,
        malware_scan=malware_scan,
    )


def _zip_member_is_symlink(info: ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _zip_member_sha256(archive: ZipFile, info: ZipInfo) -> str:
    digest = hashlib.sha256()
    with archive.open(info, "r") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_security_install_archive(
    artifact_path: Path,
    bundle_dir: Path,
    verified: VerifiedModelBundle,
) -> None:
    """Bind the authenticated transfer ZIP to the exact unpacked payload to install."""
    expected_payload = {
        str(entry["path"]): (int(entry["size_bytes"]), str(entry["sha256"]))
        for entry in verified.files
    }
    manifest_path = bundle_dir.resolve() / "manifest.json"
    signature_path = bundle_dir.resolve() / "manifest.sig"
    expected_files = set(expected_payload) | {"manifest.json"}
    if signature_path.is_file() and not signature_path.is_symlink():
        expected_files.add("manifest.sig")

    try:
        with ZipFile(artifact_path, "r") as archive:
            files: dict[str, ZipInfo] = {}
            seen: set[str] = set()
            for info in archive.infolist():
                relative = _safe_relative_path(info.filename)
                name = relative.as_posix()
                if name in seen:
                    raise ModelBundleError(f"duplicate Security Install ZIP path: {name}")
                seen.add(name)
                if _zip_member_is_symlink(info):
                    raise ModelBundleError(f"Security Install ZIP contains a symlink: {name}")
                if not info.is_dir():
                    files[name] = info
            if set(files) != expected_files:
                raise ModelBundleError("Security Install ZIP payload does not match model bundle")

            manifest_info = files["manifest.json"]
            if manifest_info.file_size > _MAX_MANIFEST_BYTES:
                raise ModelBundleError("Security Install ZIP manifest exceeds the size limit")
            if archive.read(manifest_info) != manifest_path.read_bytes():
                raise ModelBundleError("Security Install ZIP manifest does not match model bundle")

            if "manifest.sig" in expected_files:
                signature_info = files["manifest.sig"]
                if signature_info.file_size > _MAX_SIGNATURE_BYTES:
                    raise ModelBundleError("Security Install ZIP signature exceeds the size limit")
                if archive.read(signature_info) != signature_path.read_bytes():
                    raise ModelBundleError("Security Install ZIP signature does not match model bundle")

            for name, (expected_size, expected_hash) in expected_payload.items():
                info = files[name]
                if info.file_size != expected_size:
                    raise ModelBundleError(f"Security Install ZIP size mismatch for {name}")
                if _zip_member_sha256(archive, info) != expected_hash:
                    raise ModelBundleError(f"Security Install ZIP SHA-256 mismatch for {name}")
    except ModelBundleError:
        raise
    except (BadZipFile, OSError, RuntimeError, ValueError) as exc:
        raise ModelBundleError("Security Install artifact must be a readable ZIP") from exc


def _authenticated_manifest_release(
    bundle_dir: Path,
    verified: VerifiedModelBundle,
) -> AuthenticatedReleaseContext:
    """Derive release identity only from the already verified signed manifest."""
    if not verified.signature_verified or not verified.signing_key_id:
        raise ModelBundleError(
            "model installation requires a manifest authenticated by a trusted signing key"
        )
    manifest_path = bundle_dir.resolve() / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    return AuthenticatedReleaseContext(
        release_id=f"fieldora-model:{verified.model_id}:{verified.version}",
        release_digest=hashlib.sha256(manifest_bytes).hexdigest(),
        signer_key_id=verified.signing_key_id,
    )


def _require_model_security_install(
    evidence: Mapping[str, object],
    *,
    artifact_path: Path,
    access_control_database: Path | None,
    access_control_repository: object | None,
    subject_id: str,
    actual_target_version: str,
    verified: VerifiedModelBundle,
    authenticated_release: AuthenticatedReleaseContext,
) -> None:
    try:
        accepted = require_security_install(
            evidence,
            artifact_path=artifact_path,
            access_control_database=access_control_database,
            access_control_repository=access_control_repository,
            subject_id=subject_id,
            expected_package_id=artifact_path.name,
            expected_target_component=f"fieldora-model:{verified.model_id}",
            actual_target_version=actual_target_version,
            authenticated_release=authenticated_release,
        )
    except SecurityInstallAcceptanceError as exc:
        raise ModelBundleError(f"Security Install acceptance failed: {exc}") from exc
    if accepted.target_version != verified.version:
        raise ModelBundleError("Security Install target version does not match model bundle version")


def _copy_verified_file(source: Path, target: Path, entry: Mapping[str, object]) -> None:
    expected_size = int(entry["size_bytes"])
    expected_hash = str(entry["sha256"])
    if source.is_symlink():
        raise ModelBundleError(f"bundle file changed into a symlink: {entry['path']}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise ModelBundleError(f"bundle file became unreadable: {entry['path']}") from exc
    digest = hashlib.sha256()
    copied = 0
    try:
        with os.fdopen(descriptor, "rb") as input_stream, target.open("xb") as output_stream:
            if not stat.S_ISREG(os.fstat(input_stream.fileno()).st_mode):
                raise ModelBundleError(f"bundle file is no longer regular: {entry['path']}")
            for chunk in iter(lambda: input_stream.read(1024 * 1024), b""):
                copied += len(chunk)
                digest.update(chunk)
                output_stream.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    if copied != expected_size or digest.hexdigest() != expected_hash:
        target.unlink(missing_ok=True)
        raise ModelBundleError(f"bundle file changed during install staging: {entry['path']}")


def install_model_bundle(
    bundle_dir: Path,
    model_store: Path,
    *,
    security_install_artifact: Path,
    security_install_evidence: Mapping[str, object],
    access_control_database: Path | None = None,
    access_control_repository: object | None = None,
    security_install_subject: str,
    actual_target_version: str,
    authenticated_release: AuthenticatedReleaseContext | None = None,
    max_total_bytes: int = _DEFAULT_MAX_BYTES,
    trusted_signing_key: Path | None = None,
    require_signature: bool = False,
    require_clean_scan: bool = False,
) -> tuple[VerifiedModelBundle, Path]:
    verified = verify_model_bundle(
        bundle_dir,
        max_total_bytes=max_total_bytes,
        trusted_signing_key=trusted_signing_key,
        require_signature=require_signature,
        require_clean_scan=require_clean_scan,
    )
    release_context = authenticated_release or _authenticated_manifest_release(bundle_dir, verified)
    _verify_security_install_archive(security_install_artifact, bundle_dir, verified)
    _require_model_security_install(
        security_install_evidence,
        artifact_path=security_install_artifact,
        access_control_database=access_control_database,
        access_control_repository=access_control_repository,
        subject_id=security_install_subject,
        actual_target_version=actual_target_version,
        verified=verified,
        authenticated_release=release_context,
    )

    destination = model_store / verified.model_id / verified.version
    if destination.exists():
        raise ModelBundleError(f"model version is already installed: {verified.artifact_storage_id}")
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=".fieldora-model-", dir=parent))
    try:
        bundle_root = bundle_dir.resolve()
        for entry in verified.files:
            relative = PurePosixPath(str(entry["path"]))
            source = bundle_root.joinpath(*relative.parts)
            target = temp_root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy_verified_file(source, target, entry)
        (temp_root / "FIELDORA-INSTALL.json").write_text(
            json.dumps(verified.registry_record(), ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
            encoding="utf-8",
        )
        _require_model_security_install(
            security_install_evidence,
            artifact_path=security_install_artifact,
            access_control_database=access_control_database,
            subject_id=security_install_subject,
            actual_target_version=actual_target_version,
            verified=verified,
            authenticated_release=release_context,
        )
        if destination.exists():
            raise ModelBundleError(f"model version is already installed: {verified.artifact_storage_id}")
        os.replace(temp_root, destination)
    except BaseException:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    return verified, destination


def _load_security_install_evidence(path: Path) -> Mapping[str, object]:
    if path.is_symlink() or not path.is_file():
        raise ModelBundleError("Security Install evidence must be a regular non-symlink JSON file")
    try:
        if path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise ModelBundleError("Security Install evidence exceeds the configured size limit")
        value = json.loads(path.read_text(encoding="utf-8"))
    except ModelBundleError:
        raise
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ModelBundleError("Security Install evidence is unreadable or invalid JSON") from exc
    if not isinstance(value, dict):
        raise ModelBundleError("Security Install evidence must contain an object")
    return value


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
        command.add_argument("--require-clean-scan", action="store_true")
        if name == "install":
            command.add_argument("--store", type=Path, required=True)
            command.add_argument("--security-install-artifact", type=Path, required=True)
            command.add_argument("--security-install-evidence", type=Path, required=True)
            access = command.add_mutually_exclusive_group(required=True)
            access.add_argument("--access-control-database", type=Path)
            access.add_argument("--postgres-access-dsn-file", type=Path)
            command.add_argument("--security-install-subject", required=True)
            command.add_argument("--actual-target-version", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        kwargs = {
            "max_total_bytes": args.max_bytes,
            "trusted_signing_key": args.trusted_signing_key,
            "require_signature": args.require_signature,
            "require_clean_scan": args.require_clean_scan,
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
                "malware_scan": verified.malware_scan,
            }
        else:
            access_repository = None
            if args.postgres_access_dsn_file is not None:
                if (
                    not args.postgres_access_dsn_file.is_file()
                    or args.postgres_access_dsn_file.stat().st_size > 16_384
                ):
                    raise ModelBundleError("PostgreSQL access DSN file is invalid")
                access_dsn = args.postgres_access_dsn_file.read_text(encoding="utf-8").strip()
                if not access_dsn:
                    raise ModelBundleError("PostgreSQL access DSN file is empty")
                try:
                    import psycopg
                except ImportError as exc:
                    raise ModelBundleError(
                        "PostgreSQL Security Install requires the server-postgresql dependency"
                    ) from exc
                from natureai_next.server.postgres_access import PostgresAccessControlRepository

                access_repository = PostgresAccessControlRepository(
                    lambda: psycopg.connect(access_dsn, connect_timeout=10)
                )
            verified, _destination = install_model_bundle(
                args.bundle,
                args.store,
                security_install_artifact=args.security_install_artifact,
                security_install_evidence=_load_security_install_evidence(
                    args.security_install_evidence
                ),
                access_control_database=args.access_control_database,
                access_control_repository=access_repository,
                security_install_subject=args.security_install_subject,
                actual_target_version=args.actual_target_version,
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